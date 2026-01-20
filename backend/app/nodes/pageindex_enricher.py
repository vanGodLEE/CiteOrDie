"""
PageIndex条款提取节点（Enricher）
遍历PageIndex的叶子节点，为每个节点提取条款
支持文本和视觉模型双重提取（图片、表格）
"""

from typing import Dict, Any, List, Tuple
from loguru import logger
from pydantic import BaseModel, Field
import re
from pathlib import Path
from app.core.states import SectionState, ClauseItem, PageIndexNode, create_matrix_id
from app.services.llm_service import get_llm_service
from app.api.async_tasks import TaskManager
from app.core.config import settings
from app.utils.progress_helper import log_step


def pageindex_enricher_node(state: SectionState) -> Dict[str, Any]:
    """
    PageIndex条款提取节点（单个Worker）- 支持文本和视觉双重提取
    
    输入：
    - state.pageindex_node: PageIndex的一个节点（通常是叶子节点）
    - state.mineru_output_dir: MinerU输出目录（用于查找图片）
    
    输出：
    - state.clauses: 提取的条款列表（文本+视觉，会被追加到全局State）
    
    工作流程：
    1. 提取文本条款（从original_text）
    2. 识别Markdown中的图片引用
    3. 如果有图片，调用视觉模型提取图片条款
    4. 合并文本条款和视觉条款
    5. 返回完整条款列表
    """
    node = state.get("pageindex_node")
    task_id = state.get("task_id")
    mineru_output_dir = state.get("mineru_output_dir")
    
    if not node:
        logger.warning("未找到pageindex_node，跳过")
        return {"clauses": []}
    
    logger.info(f"处理节点: {node.title} (页码: {node.start_index}-{node.end_index})")
    
    # 更新任务进度
    if task_id:
        TaskManager.log_progress(
            task_id,
            f"正在提取条款: {node.title}",
            50
        )
    
    try:
        # 准备节点内容
        content = _prepare_node_content(node)
        
        # ========== 第1步：提取文本条款 ==========
        text_requirements = []
        
        if content and len(content.strip()) > 0:
            logger.info(f"节点 {node.title} 内容长度: {len(content)}字，开始提取文本条款")
            log_step(task_id, f"分析章节: {node.title} ({len(content)}字)")
            
            # 调用LLM提取文本条款
            llm_service = get_llm_service()
            log_step(task_id, "调用LLM进行结构化条款提取...")
            
            # 构建提示词
            prompt = _build_extraction_prompt(node, content)
            
            # 定义输出模型
            class ClauseList(BaseModel):
                """条款列表"""
                items: List[ClauseItem] = Field(default_factory=list, description="提取的条款列表")
            
            # 调用LLM
            messages = [
                {"role": "system", "content": "你是一个专业的文档分析专家，擅长从各类文档中提取结构化条款。"},
                {"role": "user", "content": prompt}
            ]
            
            result = llm_service.structured_completion(
                messages=messages,
                response_model=ClauseList,
                model=settings.extractor_model,
                temperature=0.1
            )
            
            text_requirements = result.items if result else []
            logger.info(f"✓ 从文本中提取到 {len(text_requirements)} 条条款")
            log_step(task_id, f"✓ 文本条款: {len(text_requirements)}条")
        else:
            logger.info(f"节点 {node.title} 无文本内容")
        
        # ========== 第2步：提取视觉条款（如果有图片） ==========
        visual_requirements = []
        
        if mineru_output_dir and content:
            # 从Markdown中识别图片
            image_paths = _extract_image_paths_from_markdown(content, mineru_output_dir)
            
            if image_paths:
                logger.info(f"节点 {node.title} 包含 {len(image_paths)} 张图片")
                log_step(task_id, f"发现{len(image_paths)}个图表，启动视觉分析")
                
                llm_service = get_llm_service()
                visual_requirements = _extract_requirements_from_images(
                    image_paths=image_paths,
                    node=node,
                    llm_service=llm_service,
                    task_id=task_id
                )
                logger.info(f"✓ 从图片中提取到 {len(visual_requirements)} 条条款")
                log_step(task_id, f"✓ 图表条款: {len(visual_requirements)}条")
        
        # ========== 第3步：合并条款并重新编号 ==========
        all_requirements = text_requirements + visual_requirements
        
        # 为所有条款重新生成matrix_id（统一编号）
        for i, req in enumerate(all_requirements, 1):
            req.matrix_id = create_matrix_id(node.node_id or "UNKNOWN", i)
            req.section_id = node.node_id or "UNKNOWN"
            req.section_title = node.title
            
            # 确保page_number正确
            if req.page_number == 0:
                req.page_number = node.start_index
        
        logger.info(
            f"✓ 节点 {node.title} 提取完成: "
            f"文本条款{len(text_requirements)}条 + 视觉条款{len(visual_requirements)}条 = "
            f"总计{len(all_requirements)}条"
        )
        
        # 记录详细信息
        for req in all_requirements:
            source_tag = "[图片]" if "[图片内容]" in req.original_text else "[文本]"
            logger.debug(f"  {source_tag} {req.matrix_id}: {req.original_text[:50]}...")
        
        # 将条款添加到节点本身（构建条款树）
        node.clauses = all_requirements
        
        return {"clauses": all_requirements}
        
    except Exception as e:
        logger.error(f"节点 {node.title} 提取失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"clauses": []}


def _prepare_node_content(node: PageIndexNode) -> str:
    """
    准备节点内容用于条款提取
    
    策略（优化后）：
    使用"标题 + 原文"的组合，让LLM在提取条款时能充分理解上下文
    """
    # 只使用original_text字段
    if node.original_text and len(node.original_text.strip()) > 0:
        # 组合标题和原文
        content = f"## {node.title}\n\n{node.original_text}"
        logger.debug(f"使用标题+original_text，总长度: {len(content)}")
        return content
    
    # original_text为空，表示该节点无正文内容
    logger.info(f"节点 {node.title} 的original_text为空，跳过条款提取")
    return ""


def _build_extraction_prompt(node: PageIndexNode, content: str) -> str:
    """
    构建条款提取的提示词（结构化版：提取可执行条款的完整结构）
    """
    prompt = f"""你是文档分析专家，专门从各类文档中提取可执行条款（Actionable Clauses）。

请分析以下章节内容，提取所有可执行条款，并对每个条款进行结构化分析。

**适用文档类型**：招标书、合同、合规制度、SOP、标准规范、政策文件、协议等各类文档。

## 章节信息
- 页码范围：{node.start_index}-{node.end_index}
- 节点ID：{node.node_id or "UNKNOWN"}

## 章节内容（标题+原文）
{content}

## 条款结构化提取（核心）

对每个条款进行以下7个维度的结构化分析：

### 1. type（条款类型）- **必填**
必须选择以下之一：
- **obligation**（义务）：必须做某事，如"甲方应提供..."、"乙方需确保..."
- **requirement**（需求）：对产品/服务的要求，如"系统需支持1000并发"、"响应时间不超过2秒"
- **prohibition**（禁止）：禁止做某事，如"不得转包"、"禁止使用..."
- **deliverable**（交付物）：需要交付的成果，如"需提交技术方案"、"需提供培训手册"
- **deadline**（截止时间）：时间节点要求，如"提交截止时间"、"交付期限"
- **penalty**（惩罚）：违约后果，如"逾期每天罚款..."、"不合格扣除保证金"
- **definition**（定义）：术语定义，如"本文档中的'系统'是指..."

### 2. actor（执行主体）- 选填
谁来执行这个条款：
- **party_a**（甲方）：文档中的第一方、委托方、采购方
- **party_b**（乙方）：文档中的第二方、承包方、供应方
- **provider**（提供方）：服务或产品提供者
- **client**（客户方）：接收服务或产品的一方
- **system**（系统）：软件系统、设备
- **organization**（组织）：项目组、监理方
- **role**（角色）：项目经理、技术负责人
- 其他具体角色名称

### 3. action（执行动作）- 选填
做什么动作：
- **submit**（提交）：提交文档、提交报告
- **provide**（提供）：提供服务、提供支持
- **ensure**（确保）：确保质量、确保安全
- **record**（记录）：记录日志、记录变更
- **comply**（遵守）：遵守规范、遵守标准
- **禁止**（如：不得、禁止、严禁）
- 其他动词

### 4. object（作用对象）- 选填
对什么产生作用：
- **document**（文档）：技术方案、报告文件
- **feature**（功能）：系统功能、业务功能
- **KPI**（指标）：性能指标、质量指标
- **material**（材料）：设备、软件、硬件
- 其他名词

### 5. condition（触发条件）- 选填
在什么条件下触发：
- **if**（如果）："如果验收不合格"、"如果出现故障"
- **when**（当）："当系统上线后"、"当合同签订后"
- **unless**（除非）："除非双方另有约定"
- 其他条件描述

### 6. deadline（时间要求）- 选填
时间限制：
- 具体日期："2024年12月31日前"
- 相对时间："合同签订后30天内"、"验收合格后15个工作日"
- 周期性："每月5日前"、"每季度末"

### 7. metric（量化指标）- 选填
可量化的标准：
- 数值："1000个并发用户"、"响应时间2秒"
- 范围："50-100万元"、"3-5年经验"
- 比较运算符：">= 500万"、"<= 10%"、"≥ 99.9%"

## 提取策略

**智能识别标题和原文**：
- 标题包含明确条款 → 从标题提取
- 标题仅是分类 → 从原文提取
- 标题和原文都有条款 → 分别提取

**识别表格来源**：
- 如果内容包含`【表格：images/xxx.jpg】`标记，填充`img_path`和`table_caption`字段

## 输出字段说明

每个条款必须包含以下字段：

### 必填字段：
- **type**：条款类型（obligation/requirement/prohibition/deliverable/deadline/penalty/definition）
- **original_text**：条款原文（从标题或原文中精确摘录）
- **page_number**：页码（使用 {node.start_index}）

### 结构化字段（尽量填写）：
- **actor**：执行主体（supplier/buyer/system/organization/role/其他）
- **action**：执行动作（submit/provide/ensure/record/comply/禁止.../其他动词）
- **object**：作用对象（document/feature/KPI/material/其他名词）
- **condition**：触发条件（if/when/unless等条件描述）
- **deadline**：时间要求（具体日期、相对时间、周期性要求）
- **metric**：量化指标（具体数值、范围、比较运算符）

### 辅助字段：
- **img_path**：图片/表格路径（如"images/xxx.jpg"）
- **image_caption**：图片描述（字符串）
- **table_caption**：表格标题（字符串）

## 提取原则

1. **完整性**：提取所有可执行条款，不遗漏
2. **准确性**：original_text必须精确摘录，不要改写
3. **结构化**：尽量填写所有7个结构化字段（type, actor, action, object, condition, deadline, metric）
4. **可执行性**：只提取明确的、可执行的条款，跳过描述性文字

## 输出格式
严格按照ClauseItem模型输出JSON列表。

## 示例说明

**示例1：需求类条款（requirement）**
```
## 系统需支持1000个并发用户，响应时间不超过2秒
```
提取为：
```json
{{
  "type": "requirement",
  "actor": "system",
  "action": "support",
  "object": "concurrent users",
  "condition": null,
  "deadline": null,
  "metric": "1000并发用户，响应时间≤2秒",
  "original_text": "系统需支持1000个并发用户，响应时间不超过2秒",
  "page_number": {node.start_index}
}}
```

**示例2：义务类条款（obligation）**
```
## 付款方式

合同签订后预付30%，验收合格后支付60%，质保期满支付尾款10%。
```
提取为：
```json
{{
  "type": "obligation",
  "actor": "buyer",
  "action": "pay",
  "object": "contract amount",
  "condition": "合同签订后、验收合格后、质保期满",
  "deadline": "分三期",
  "metric": "预付30%、验收60%、质保10%",
  "original_text": "合同签订后预付30%，验收合格后支付60%，质保期满支付尾款10%。",
  "page_number": {node.start_index}
}}
```

**示例3：交付物类条款（deliverable）**
```
乙方需提供技术方案、实施方案和培训计划各一份。
```
提取为：
```json
{{
  "type": "deliverable",
  "actor": "party_b",
  "action": "provide",
  "object": "technical documents",
  "condition": null,
  "deadline": null,
  "metric": "技术方案、实施方案、培训计划各一份",
  "original_text": "乙方需提供技术方案、实施方案和培训计划各一份。",
  "page_number": {node.start_index}
}}
```

**示例4：截止时间类条款（deadline）**
```
文件递交截止时间：2024年12月31日上午10:00（北京时间）
```
提取为：
```json
{{
  "type": "deadline",
  "actor": "party_b",
  "action": "submit",
  "object": "bidding documents",
  "condition": null,
  "deadline": "2024年12月31日上午10:00",
  "metric": null,
  "original_text": "投标文件递交截止时间：2024年12月31日上午10:00（北京时间）",
  "page_number": {node.start_index}
}}
```

**示例5：禁止类条款（prohibition）**
```
投标人不得转包或违法分包。
```
提取为：
```json
{{
  "type": "prohibition",
  "actor": "supplier",
  "action": "禁止",
  "object": "subcontracting",
  "condition": null,
  "deadline": null,
  "metric": null,
  "original_text": "投标人不得转包或违法分包。",
  "page_number": {node.start_index}
}}
```

**示例6：惩罚类条款（penalty）**
```
逾期交付的，每逾期一天，按合同总价的0.5%支付违约金。
```
提取为：
```json
{{
  "type": "penalty",
  "actor": "supplier",
  "action": "pay",
  "object": "penalty",
  "condition": "when 逾期交付",
  "deadline": null,
  "metric": "每天0.5%合同总价",
  "original_text": "逾期交付的，每逾期一天，按合同总价的0.5%支付违约金。",
  "page_number": {node.start_index}
}}
```

**示例7：表格条款（table）**
```
【表格：images/table_1.jpg】技术参数要求

参数名称 | 最低要求 | 评分标准
---------|----------|----------
CPU | 8核心 | 12核心满分
内存 | 16GB | 32GB满分
存储 | 500GB SSD | 1TB SSD满分
```
提取为（每行一个条款）：
```json
{{
  "type": "requirement",
  "actor": "system",
  "action": "meet",
  "object": "technical specifications",
  "condition": null,
  "deadline": null,
  "metric": "CPU≥8核心",
  "original_text": "CPU最低要求8核心",
  "page_number": {node.start_index},
  "img_path": "images/table_1.jpg",
  "table_caption": "技术参数要求"
}}
```

**重要提示**：
- 每个条款都必须填写type字段
- actor, action, object, condition, deadline, metric尽量填写，如果没有则填null
- original_text必须精确摘录原文
- **识别表格标记**：如果内容包含`【表格：images/xxx.jpg】`，必须将路径填充到`img_path`字段，表格标题填充到`table_caption`字段
- **表格条款逐行提取**：表格中的每一行数据可能是一个独立的条款，每个条款都要填充相同的`img_path`和`table_caption`
"""
    return prompt


def _extract_image_paths_from_markdown(content: str, mineru_output_dir: str) -> List[Tuple[str, str]]:
    """
    从Markdown内容中提取图片路径（返回元组：绝对路径和相对路径）
    
    Args:
        content: Markdown内容
        mineru_output_dir: MinerU输出目录
        
    Returns:
        图片路径元组列表：[(绝对路径, 相对路径), ...]
        相对路径用于存储到img_path字段，绝对路径用于视觉模型调用
    """
    # Markdown图片格式：![description](path)
    image_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    matches = re.findall(image_pattern, content)
    
    if not matches:
        return []
    
    image_path_tuples = []
    mineru_dir = Path(mineru_output_dir)
    
    for description, rel_path in matches:
        # rel_path 可能是相对路径，如 "images/image_1.png"
        # 需要转换为绝对路径
        abs_path = mineru_dir / rel_path
        
        if abs_path.exists():
            image_path_tuples.append((str(abs_path), rel_path))
            logger.debug(f"找到图片: {rel_path} -> {abs_path}")
        else:
            logger.warning(f"图片文件不存在: {abs_path}")
    
    return image_path_tuples


def _extract_requirements_from_images(
    image_paths: List[Tuple[str, str]],
    node: PageIndexNode,
    llm_service: Any,
    task_id: str = None
) -> List[ClauseItem]:
    """
    ✅ 优化：逐张图片调用视觉模型提取条款
    
    Args:
        image_paths: 图片路径元组列表 [(绝对路径, 相对路径), ...]
        node: 节点对象
        llm_service: LLM服务实例
        
    Returns:
        从所有图片中提取的条款列表（每个条款都精确填充img_path）
    """
    if not image_paths:
        return []
    
    logger.info(f"节点 {node.title} 包含 {len(image_paths)} 张图片，逐张提取条款")
    
    all_requirements = []
    
    # ✅ 关键改进：逐张图片处理，而不是批量处理
    for idx, (abs_path, rel_path) in enumerate(image_paths, 1):
        logger.info(f"  处理第 {idx}/{len(image_paths)} 张图片: {rel_path}")
        log_step(task_id, f"视觉分析 {idx}/{len(image_paths)}: {rel_path}")
        
        try:
            # 构建单张图片的提示词
            prompt = f"""你是文档分析专家。请分析这张图片内容，提取其中的可执行条款。

## 上下文信息
- 章节标题：{node.title}
- 页码范围：{node.start_index}-{node.end_index}
- 节点ID：{node.node_id or "UNKNOWN"}
- 当前图片：{rel_path}

## 任务说明
这张图片来自文档的"{node.title}"章节。请仔细分析图片中的内容：
- 如果是**表格**：提取表格中的可执行条款（义务、需求、交付物、时间等）
- 如果是**流程图/架构图**：提取系统架构要求、技术选型要求、部署要求等
- 如果是**截图/示例**：提取界面要求、功能要求、用户体验要求等
- 如果是**其他图示**：提取图片传达的关键条款信息

## 提取要求
1. **准确性**：只提取明确的条款，不要推测或添加图片中没有的内容
2. **完整性**：不要遗漏图片中的重要条款
3. **结构化**：对每个条款进行结构化分析（type, actor, action, object, condition, deadline, metric）
4. **来源标注**：original_text字段填写"[图片内容] "加上具体描述
5. **caption填充**：
   - 如果是图片（架构图/流程图/截图等），填充image_caption字段
   - 如果是表格，填充table_caption字段
   - caption应包含图片/表格的完整描述和关键信息

## 条款类型说明
- **obligation**（义务）：必须做某事
- **requirement**（需求）：对产品/服务的要求
- **prohibition**（禁止）：禁止做某事
- **deliverable**（交付物）：需要交付的成果
- **deadline**（截止时间）：时间节点要求
- **penalty**（惩罚）：违约后果
- **definition**（定义）：术语定义

## 输出格式
请以JSON数组格式输出条款列表，每个条款包含：
- type: 条款类型（必填）
- actor: 执行主体（选填）
- action: 执行动作（选填）
- object: 作用对象（选填）
- condition: 触发条件（选填）
- deadline: 时间要求（选填）
- metric: 量化指标（选填）
- original_text: "[图片内容] " + 图片中的具体描述
- page_number: {node.start_index}
- image_caption: 图片内容完整描述（仅当内容来自普通图片时填写）
- table_caption: 表格内容完整描述（仅当内容来自表格时填写）

如果图片中没有条款信息，返回空数组[]。
"""
            
            # ✅ 单张图片调用视觉模型
            response_text = llm_service.vision_completion(
                text_prompt=prompt,
                image_inputs=[abs_path],  # 单张图片
                temperature=0.2,
                max_tokens=4000  # 单张图片4000足够
            )
            
            # 解析JSON响应
            import json
            try:
                # 尝试提取JSON数组
                json_match = re.search(r'\[[\s\S]*\]', response_text)
                if json_match:
                    requirements_data = json.loads(json_match.group())
                else:
                    logger.warning(f"图片 {rel_path} 的视觉模型返回不包含JSON数组")
                    continue
                
                # 转换为ClauseItem对象
                for i, req_data in enumerate(requirements_data, 1):
                    # 补充必需字段
                    req_data.setdefault('section_id', node.node_id or "UNKNOWN")
                    req_data.setdefault('section_title', node.title)
                    req_data.setdefault('page_number', node.start_index)
                    req_data.setdefault('type', 'requirement')  # 默认类型
                    
                    # ✅ 关键：精确填充img_path（我们确切知道这个条款来自哪张图片）
                    req_data['img_path'] = rel_path
                    
                    # ✅ 修复：先分配临时matrix_id（后续会统一重新编号）
                    temp_matrix_id = create_matrix_id(node.node_id or "UNKNOWN", len(all_requirements) + i)
                    req_data.setdefault('matrix_id', temp_matrix_id)
                    
                    # 创建ClauseItem
                    req = ClauseItem(**req_data)
                    all_requirements.append(req)
                
                logger.info(f"  ✓ 图片 {rel_path} 提取到 {len(requirements_data)} 条条款")
                
            except json.JSONDecodeError as e:
                logger.error(f"图片 {rel_path} 的JSON解析失败: {e}")
                logger.debug(f"原始返回: {response_text[:200]}")
                continue
            
        except Exception as e:
            logger.error(f"图片 {rel_path} 处理失败: {e}")
            continue
    
    # 为所有条款统一编号（跨图片连续编号）
    for i, req in enumerate(all_requirements, 1):
        req.matrix_id = create_matrix_id(node.node_id or "UNKNOWN", i)
    
    logger.info(f"✓ 从 {len(image_paths)} 张图片中总计提取到 {len(all_requirements)} 条条款")
    return all_requirements
