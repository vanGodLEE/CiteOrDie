"""
PageIndex需求提取节点（Enricher）
遍历PageIndex的叶子节点，为每个节点提取需求
支持文本和视觉模型双重提取（图片、表格）
"""

from typing import Dict, Any, List, Tuple
from loguru import logger
from pydantic import BaseModel, Field
import re
from pathlib import Path
from app.core.states import SectionState, RequirementItem, PageIndexNode, create_matrix_id
from app.services.llm_service import get_llm_service
from app.api.async_tasks import TaskManager
from app.core.config import settings


def pageindex_enricher_node(state: SectionState) -> Dict[str, Any]:
    """
    PageIndex需求提取节点（单个Worker）- 支持文本和视觉双重提取
    
    输入：
    - state.pageindex_node: PageIndex的一个节点（通常是叶子节点）
    - state.mineru_output_dir: MinerU输出目录（用于查找图片）
    
    输出：
    - state.requirements: 提取的需求列表（文本+视觉，会被追加到全局State）
    
    工作流程：
    1. 提取文本需求（从original_text）
    2. 识别Markdown中的图片引用
    3. 如果有图片，调用视觉模型提取图片需求
    4. 合并文本需求和视觉需求
    5. 返回完整需求列表
    """
    node = state.get("pageindex_node")
    task_id = state.get("task_id")
    mineru_output_dir = state.get("mineru_output_dir")
    
    if not node:
        logger.warning("未找到pageindex_node，跳过")
        return {"requirements": []}
    
    logger.info(f"处理节点: {node.title} (页码: {node.start_index}-{node.end_index})")
    
    # 更新任务进度
    if task_id:
        TaskManager.log_progress(
            task_id,
            f"正在提取需求: {node.title}",
            50
        )
    
    try:
        # 准备节点内容
        content = _prepare_node_content(node)
        
        # ========== 第1步：提取文本需求 ==========
        text_requirements = []
        
        if content and len(content.strip()) > 0:
            logger.info(f"节点 {node.title} 内容长度: {len(content)}字，开始提取文本需求")
            
            # 调用LLM提取文本需求
            llm_service = get_llm_service()
            
            # 构建提示词
            prompt = _build_extraction_prompt(node, content)
            
            # 定义输出模型
            class RequirementList(BaseModel):
                """需求列表"""
                items: List[RequirementItem] = Field(default_factory=list, description="提取的需求列表")
            
            # 调用LLM
            messages = [
                {"role": "system", "content": "你是一个专业的招标需求分析专家。"},
                {"role": "user", "content": prompt}
            ]
            
            result = llm_service.structured_completion(
                messages=messages,
                response_model=RequirementList,
                model=settings.extractor_model,
                temperature=0.1
            )
            
            text_requirements = result.items if result else []
            logger.info(f"✓ 从文本中提取到 {len(text_requirements)} 条需求")
        else:
            logger.info(f"节点 {node.title} 无文本内容")
        
        # ========== 第2步：提取视觉需求（如果有图片） ==========
        visual_requirements = []
        
        if mineru_output_dir and content:
            # 从Markdown中识别图片
            image_paths = _extract_image_paths_from_markdown(content, mineru_output_dir)
            
            if image_paths:
                logger.info(f"节点 {node.title} 包含 {len(image_paths)} 张图片")
                llm_service = get_llm_service()
                visual_requirements = _extract_requirements_from_images(
                    image_paths=image_paths,
                    node=node,
                    llm_service=llm_service
                )
                logger.info(f"✓ 从图片中提取到 {len(visual_requirements)} 条需求")
        
        # ========== 第3步：合并需求并重新编号 ==========
        all_requirements = text_requirements + visual_requirements
        
        # 为所有需求重新生成matrix_id（统一编号）
        for i, req in enumerate(all_requirements, 1):
            req.matrix_id = create_matrix_id(node.node_id or "UNKNOWN", i)
            req.section_id = node.node_id or "UNKNOWN"
            req.section_title = node.title
            
            # 确保page_number正确
            if req.page_number == 0:
                req.page_number = node.start_index
        
        logger.info(
            f"✓ 节点 {node.title} 提取完成: "
            f"文本需求{len(text_requirements)}条 + 视觉需求{len(visual_requirements)}条 = "
            f"总计{len(all_requirements)}条"
        )
        
        # 记录详细信息
        for req in all_requirements:
            source_tag = "[图片]" if "[图片内容]" in req.original_text else "[文本]"
            logger.debug(f"  {source_tag} {req.matrix_id}: {req.requirement[:50]}...")
        
        # 将需求添加到节点本身（构建需求树）
        node.requirements = all_requirements
        
        return {"requirements": all_requirements}
        
    except Exception as e:
        logger.error(f"节点 {node.title} 提取失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"requirements": []}


def _prepare_node_content(node: PageIndexNode) -> str:
    """
    准备节点内容用于需求提取
    
    策略（优化后）：
    使用"标题 + 原文"的组合，让LLM在提取需求时能充分理解上下文
    """
    # 只使用original_text字段
    if node.original_text and len(node.original_text.strip()) > 0:
        # 组合标题和原文
        content = f"## {node.title}\n\n{node.original_text}"
        logger.debug(f"使用标题+original_text，总长度: {len(content)}")
        return content
    
    # original_text为空，表示该节点无正文内容
    logger.info(f"节点 {node.title} 的original_text为空，跳过需求提取")
    return ""


def _build_extraction_prompt(node: PageIndexNode, content: str) -> str:
    """
    构建需求提取的提示词（智能版：处理标题中的需求 + 类型分类 + 表格识别）
    """
    prompt = f"""你是招标文件分析专家。请分析以下章节内容（包含标题和原文），提取所有招标需求，并对每个需求进行分类。

## 章节信息
- 页码范围：{node.start_index}-{node.end_index}
- 节点ID：{node.node_id or "UNKNOWN"}

## 章节内容（标题+原文）
{content}

## 提取策略（重要）

**智能识别标题中的需求**：
1. **长标题/详细标题**：如果标题本身包含具体需求（如"系统需支持1000并发用户"、"响应时间不超过2秒"），请从标题中提取需求
2. **短标题/分类标题**：如果标题只是分类名称（如"性能要求"、"技术规范"），则从原文中提取需求
3. **综合情况**：标题和原文都可能包含需求，请两者都仔细分析，避免遗漏

**识别表格来源（新增）**：
- 如果内容包含`【表格：images/xxx.jpg】`标记，说明这是表格内容
- 提取表格中的需求时，必须填充`img_path`字段（从标记中提取）
- 同时填充`table_caption`字段（从标记后的标题文本提取）
- 示例：
  ```
  【表格：images/abc.jpg】投标人须知前附表
  条款号 | 条款名称 | 编列内容
  1.1.2 | 招标人 | 名称：江麓机电集团
  ```
  提取时：
  - img_path: "images/abc.jpg"
  - table_caption: ["投标人须知前附表"]
  - original_text: "【表格：images/abc.jpg】投标人须知前附表\n条款号 | 条款名称 | ..."

**提取来源判断**：
- 标题包含明确需求 → 从标题提取，original_text填写标题内容
- 标题仅是分类 → 从原文提取，original_text填写原文内容
- 标题和原文都有需求 → 分别提取，各自记录original_text
- **表格内容** → 提取需求，original_text保留完整表格文本，img_path填充路径

## 需求类型分类（新增）

为每个提取的需求判断类型（category字段），必须选择以下之一：

1. **SOLUTION**（技术/服务方案）
   - 必须在技术方案或服务方案中详细响应的需求
   - 包括：功能、性能、架构、技术选型、实施方法、人员投入、保障措施、SLA、风险控制、交付物等
   - 示例："系统需采用B/S架构"、"响应时间不超过2秒"、"需提供实施方案"、"需配备项目经理"

2. **QUALIFICATION**（资质/资格）
   - 企业资质、证书、授权、业绩、财务、信誉、人员证书等
   - 通常放在资质文件或商务文件中，不需要在方案正文中逐条响应
   - 示例："需提供ISO9001证书"、"注册资金不少于500万"、"近三年类似项目业绩"

3. **BUSINESS**（商务条款）
   - 报价、付款、税率、合同条款、投标有效期、交货期、保函等
   - 示例："付款方式为分期付款"、"投标有效期90天"、"需缴纳履约保证金"

4. **FORMAT**（格式要求）
   - 投标文件的格式、目录、装订、签章、页码、密封、递交方式等
   - 示例："投标文件需加盖公章"、"需提供PDF和纸质版各一份"

5. **PROCESS**（流程要求）
   - 招投标流程相关的要求（报名、澄清、答疑、开标、电子标、CA、保证金缴纳等）
   - 示例："需在规定时间参加现场答疑"、"需使用CA证书加密投标文件"

6. **OTHER**（其他/不确定）
   - 不确定或难以归类的需求
   - 需要人工确认的情况
   - 示例："需提供某方案说明"但不明确属于技术还是商务

**分类判断原则**：
- 优先判断是否需要在技术/服务方案中响应（SOLUTION）
- 资质类、商务类、格式类比较明确，容易判断
- 如果不确定，标记为OTHER，由人工后续确认

## 提取规则

1. **需求范围**：提取所有招标需求，包括：
   - 功能需求：系统功能、业务流程
   - 技术需求：技术架构、开发语言、框架
   - 性能需求：响应时间、并发量、可用性
   - 质量需求：安全性、可维护性、可扩展性
   - 部署需求：部署环境、服务器配置
   - 实施需求：实施计划、培训要求
   - 服务需求：售后服务、运维支持
   - 资质需求：企业资质、人员证书
   - 商务需求：付款、合同条款
   - 格式需求：文件格式、装订
   - 流程需求：报名、开标流程

2. **提取要点**：
   - requirement：用简洁的语言概括需求（1-2句话）
   - original_text：**从标题或原文中精确摘录**（根据需求来源）
   - page_number：需求所在的页码（使用start_index: {node.start_index}）
   - **category**：需求类型（SOLUTION/QUALIFICATION/BUSINESS/FORMAT/PROCESS/OTHER）
   - response_suggestion：建议的应答方向（1句话，结合category）
   - risk_warning：潜在风险提示（如果有，没有则填"无"）
   - notes：其他备注（如果有，没有则填"无"）
   - **img_path**：图片/表格路径（字符串，如"images/xxx.jpg"，从标记中提取）
   - **image_caption**：图片描述（字符串，不是列表！）
   - **table_caption**：表格标题（字符串，不是列表！如"投标人须知前附表"）

3. **重要提醒**：
    - 上述内容已包含章节标题和精确原文
    - 标题可能本身就是需求，也可能只是分类标签，请智能判断
    - 原文是精确提取的内容，仅包含该标题下的内容
    - 不会包含其他标题的内容，因此**无需担心重复**
    - 请结合标题和原文，充分提取所有需求，一个都不要遗漏
    - **每个需求都必须指定category字段**

## 输出格式
严格按照RequirementItem模型输出JSON列表。

## 示例说明

**示例1：技术方案类需求（SOLUTION）**
```
## 系统需支持1000个并发用户，响应时间不超过2秒

（原文为空或仅有补充说明）
```
应提取为：
- requirement: "系统需支持1000个并发用户，响应时间不超过2秒"
- original_text: "系统需支持1000个并发用户，响应时间不超过2秒"（从标题提取）
- page_number: {node.start_index}
- category: "SOLUTION"
- response_suggestion: "在技术方案中说明系统架构设计和性能优化方案"
- risk_warning: "需要进行压力测试验证性能指标"
- notes: "关键性能指标"
- img_path: ""（非图片/表格需求，保持为空）
- image_caption: []
- table_caption: []

**示例2：资质类需求（QUALIFICATION）**
```
## 资质要求

投标人需具有ISO9001质量管理体系认证证书，注册资金不少于500万元。
```
应提取为：
- requirement: "需具有ISO9001证书，注册资金≥500万"
- original_text: "投标人需具有ISO9001质量管理体系认证证书，注册资金不少于500万元。"
- page_number: {node.start_index}
- category: "QUALIFICATION"
- response_suggestion: "在资质文件中提供ISO9001证书复印件和营业执照"
- risk_warning: "确认证书在有效期内"
- notes: "资质门槛要求"

**示例3：商务类需求（BUSINESS）**
```
## 付款方式

合同签订后预付30%，验收合格后支付60%，质保期满支付尾款10%。
```
应提取为：
- requirement: "分三期付款：预付30%、验收60%、质保10%"
- original_text: "合同签订后预付30%，验收合格后支付60%，质保期满支付尾款10%。"
- page_number: {node.start_index}
- category: "BUSINESS"
- response_suggestion: "在商务报价中明确付款节点和金额"
- risk_warning: "注意现金流管理"
- notes: "标准分期付款条款"

**示例4：混合类型（标题和原文都有需求）**
```
## 系统需采用B/S架构

前端需支持Chrome、Firefox、Safari等主流浏览器，后端需支持分布式部署。投标人需提供软件著作权证书。
```
应提取为三条需求：
1. requirement: "系统需采用B/S架构"
   original_text: "系统需采用B/S架构"（从标题提取）
   category: "SOLUTION"
   
2. requirement: "前端支持主流浏览器，后端支持分布式部署"
   original_text: "前端需支持Chrome、Firefox、Safari等主流浏览器，后端需支持分布式部署。"
   category: "SOLUTION"
   
3. requirement: "需提供软件著作权证书"
   original_text: "投标人需提供软件著作权证书。"
   category: "QUALIFICATION"

**示例5：表格类需求（SOLUTION/QUALIFICATION/BUSINESS等）**
```
【表格：images/table_123.jpg】投标人须知前附表
条款号 | 条款名称 | 编列内容
1.1.2 | 招标人 | 名称：江麓机电集团有限公司
1.1.3 | 招标代理机构 | 名称：北京五环国际工程管理有限公司
1.3.2 | 交货期 | 合同生效后3个月内
```
应提取为：
1. requirement: "招标人为江麓机电集团有限公司"
   original_text: "【表格：images/table_123.jpg】投标人须知前附表\n条款号 | 条款名称 | 编列内容\n1.1.2 | 招标人 | 名称：江麓机电集团有限公司"
   category: "BUSINESS"
   img_path: "images/table_123.jpg"
   table_caption: "投标人须知前附表"
   
2. requirement: "招标代理机构为北京五环国际工程管理有限公司"
   original_text: "【表格：images/table_123.jpg】投标人须知前附表\n条款号 | 条款名称 | 编列内容\n1.1.3 | 招标代理机构 | 名称：北京五环国际工程管理有限公司"
   category: "BUSINESS"
   img_path: "images/table_123.jpg"
   table_caption: "投标人须知前附表"
   
3. requirement: "交货期为合同生效后3个月内"
   original_text: "【表格：images/table_123.jpg】投标人须知前附表\n条款号 | 条款名称 | 编列内容\n1.3.2 | 交货期 | 合同生效后3个月内"
   category: "BUSINESS"
   img_path: "images/table_123.jpg"
   table_caption: "投标人须知前附表"

**重要提示**：
- 表格中的每个需求行都应单独提取
- 所有从同一表格提取的需求共享相同的img_path和table_caption
- original_text应包含表格标记、标题和具体行的内容
- img_path是后续需求定位的关键，必须准确填充
- **table_caption和image_caption必须是字符串格式，绝对不要使用列表！**
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
    llm_service: Any
) -> List[RequirementItem]:
    """
    ✅ 优化：逐张图片调用视觉模型提取需求
    
    Args:
        image_paths: 图片路径元组列表 [(绝对路径, 相对路径), ...]
        node: 节点对象
        llm_service: LLM服务实例
        
    Returns:
        从所有图片中提取的需求列表（每个需求都精确填充img_path）
    """
    if not image_paths:
        return []
    
    logger.info(f"节点 {node.title} 包含 {len(image_paths)} 张图片，逐张提取需求")
    
    all_requirements = []
    
    # ✅ 关键改进：逐张图片处理，而不是批量处理
    for idx, (abs_path, rel_path) in enumerate(image_paths, 1):
        logger.info(f"  处理第 {idx}/{len(image_paths)} 张图片: {rel_path}")
        
        try:
            # 构建单张图片的提示词
            prompt = f"""你是招标文件分析专家。请分析这张图片内容，提取其中的招标需求。

## 上下文信息
- 章节标题：{node.title}
- 页码范围：{node.start_index}-{node.end_index}
- 节点ID：{node.node_id or "UNKNOWN"}
- 当前图片：{rel_path}

## 任务说明
这张图片来自招标文件的"{node.title}"章节。请仔细分析图片中的内容：
- 如果是**表格**：提取表格中的技术参数、规格要求、性能指标等
- 如果是**流程图/架构图**：提取系统架构要求、技术选型要求、部署要求等
- 如果是**截图/示例**：提取界面要求、功能要求、用户体验要求等
- 如果是**其他图示**：提取图片传达的关键需求信息

## 提取要求
1. **准确性**：只提取明确的需求，不要推测或添加图片中没有的内容
2. **完整性**：不要遗漏图片中的重要需求
3. **分类**：对每个需求进行类型分类（SOLUTION/QUALIFICATION/BUSINESS/FORMAT/PROCESS/OTHER）
4. **来源标注**：original_text字段填写"[图片内容] "加上具体描述
5. **caption填充**：
   - 如果是图片（架构图/流程图/截图等），填充image_caption字段
   - 如果是表格，填充table_caption字段
   - caption应包含图片/表格的完整描述和关键信息

## 需求类型说明
- **SOLUTION**（技术/服务方案）：功能、性能、架构、技术选型等
- **QUALIFICATION**（资质）：企业资质、证书、授权、业绩等
- **BUSINESS**（商务）：报价、付款、合同条款等
- **FORMAT**（格式）：文件格式、装订、签章等
- **PROCESS**（流程）：报名、开标、电子标等流程要求
- **OTHER**（其他）：不确定的需求

## 输出格式
请以JSON数组格式输出需求列表，每个需求包含：
- requirement: 需求概述（1-2句话）
- original_text: "[图片内容] " + 图片中的具体描述
- page_number: {node.start_index}
- category: 需求类型（见上述分类）
- response_suggestion: 应答建议
- risk_warning: 风险提示（如果没有填"无"）
- notes: 备注（如果没有填"图片来源"）
- image_caption: 图片内容完整描述（仅当内容来自普通图片时填写）
- table_caption: 表格内容完整描述（仅当内容来自表格时填写）

如果图片中没有需求信息，返回空数组[]。
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
                
                # 转换为RequirementItem对象
                for i, req_data in enumerate(requirements_data, 1):
                    # 补充必需字段
                    req_data.setdefault('section_id', node.node_id or "UNKNOWN")
                    req_data.setdefault('section_title', node.title)
                    req_data.setdefault('page_number', node.start_index)
                    req_data.setdefault('category', 'OTHER')
                    req_data.setdefault('response_suggestion', '请在方案中响应此图片内容')
                    req_data.setdefault('risk_warning', '无')
                    req_data.setdefault('notes', '图片来源')
                    
                    # ✅ 关键：精确填充img_path（我们确切知道这个需求来自哪张图片）
                    req_data['img_path'] = rel_path
                    
                    # ✅ 修复：先分配临时matrix_id（后续会统一重新编号）
                    temp_matrix_id = create_matrix_id(node.node_id or "UNKNOWN", len(all_requirements) + i)
                    req_data.setdefault('matrix_id', temp_matrix_id)
                    
                    # 创建RequirementItem
                    req = RequirementItem(**req_data)
                    all_requirements.append(req)
                
                logger.info(f"  ✓ 图片 {rel_path} 提取到 {len(requirements_data)} 条需求")
                
            except json.JSONDecodeError as e:
                logger.error(f"图片 {rel_path} 的JSON解析失败: {e}")
                logger.debug(f"原始返回: {response_text[:200]}")
                continue
            
        except Exception as e:
            logger.error(f"图片 {rel_path} 处理失败: {e}")
            continue
    
    # 为所有需求统一编号（跨图片连续编号）
    for i, req in enumerate(all_requirements, 1):
        req.matrix_id = create_matrix_id(node.node_id or "UNKNOWN", i)
    
    logger.info(f"✓ 从 {len(image_paths)} 张图片中总计提取到 {len(all_requirements)} 条需求")
    return all_requirements
