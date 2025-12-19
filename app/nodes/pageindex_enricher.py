"""
PageIndex需求提取节点（Enricher）
遍历PageIndex的叶子节点，为每个节点提取需求
"""

from typing import Dict, Any, List
from loguru import logger
from pydantic import BaseModel, Field
from app.core.states import SectionState, RequirementItem, PageIndexNode, create_matrix_id
from app.services.llm_service import get_llm_service
from app.api.async_tasks import TaskManager
from app.core.config import settings


def pageindex_enricher_node(state: SectionState) -> Dict[str, Any]:
    """
    PageIndex需求提取节点（单个Worker）
    
    输入：
    - state.pageindex_node: PageIndex的一个节点（通常是叶子节点）
    
    输出：
    - state.requirements: 提取的需求列表（会被追加到全局State）
    
    工作流程：
    1. 获取节点的summary或text
    2. 调用LLM提取需求
    3. 为每个需求生成matrix_id
    4. 返回需求列表
    """
    node = state.get("pageindex_node")
    task_id = state.get("task_id")
    
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
        
        # 只要有内容就尝试提取需求，让LLM判断是否包含需求
        if not content or len(content.strip()) == 0:
            logger.info(f"节点 {node.title} 无内容，跳过")
            return {"requirements": []}
        
        logger.info(f"节点 {node.title} 内容长度: {len(content)}字，开始提取需求")
        
        # 调用LLM提取需求
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
        
        requirements = result.items if result else []
        
        # 为每个需求生成matrix_id
        for i, req in enumerate(requirements, 1):
            if not req.matrix_id or req.matrix_id == "":
                req.matrix_id = create_matrix_id(node.node_id or "UNKNOWN", i)
            
            # 确保section_id和section_title正确
            req.section_id = node.node_id or "UNKNOWN"
            req.section_title = node.title
            
            # 确保page_number正确
            if req.page_number == 0:
                req.page_number = node.start_index
        
        logger.info(f"✓ 节点 {node.title} 提取到 {len(requirements)} 条需求")
        
        # 记录详细信息
        for req in requirements:
            logger.debug(f"  - {req.matrix_id}: {req.requirement[:50]}...")
        
        # 将需求添加到节点本身（构建需求树）
        node.requirements = requirements
        
        return {"requirements": requirements}
        
    except Exception as e:
        logger.error(f"节点 {node.title} 提取失败: {str(e)}")
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
    构建需求提取的提示词（智能版：处理标题中的需求）
    """
    prompt = f"""你是招标文件分析专家。请分析以下章节内容（包含标题和原文），提取所有招标需求。

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

**提取来源判断**：
- 标题包含明确需求 → 从标题提取，original_text填写标题内容
- 标题仅是分类 → 从原文提取，original_text填写原文内容
- 标题和原文都有需求 → 分别提取，各自记录original_text

## 提取规则

1. **需求范围**：提取所有招标需求，包括：
   - 功能需求：系统功能、业务流程
   - 技术需求：技术架构、开发语言、框架
   - 性能需求：响应时间、并发量、可用性
   - 质量需求：安全性、可维护性、可扩展性
   - 部署需求：部署环境、服务器配置
   - 实施需求：实施计划、培训要求
   - 服务需求：售后服务、运维支持

2. **排除内容**：
   - 商务资质要求（如注册资金、企业规模）
   - 合同条款（如付款方式、违约责任）
   - 投标文件格式要求

3. **提取要点**：
   - requirement：用简洁的语言概括需求（1-2句话）
   - original_text：**从标题或原文中精确摘录**（根据需求来源）
   - page_number：需求所在的页码（使用start_index: {node.start_index}）
   - response_suggestion：建议的应答方向（1句话）
   - risk_warning：潜在风险提示（如果有，没有则填"无"）
   - notes：其他备注（如果有，没有则填"无"）

4. **重要提醒**：
    - 上述内容已包含章节标题和精确原文
    - 标题可能本身就是需求，也可能只是分类标签，请智能判断
    - 原文是精确提取的内容，仅包含该标题下的内容
    - 不会包含其他标题的内容，因此**无需担心重复**
    - 请结合标题和原文，充分提取所有需求，一个都不要遗漏

## 输出格式
严格按照RequirementItem模型输出JSON列表。

## 示例说明

**示例1：长标题包含具体需求**
```
## 系统需支持1000个并发用户，响应时间不超过2秒

（原文为空或仅有补充说明）
```
应提取为：
- requirement: "系统需支持1000个并发用户，响应时间不超过2秒"
- original_text: "系统需支持1000个并发用户，响应时间不超过2秒"（从标题提取）
- page_number: {node.start_index}
- response_suggestion: "在技术方案中说明系统架构设计和性能优化方案"
- risk_warning: "需要进行压力测试验证性能指标"
- notes: "关键性能指标，来自标题"

**示例2：短标题，需求在原文中**
```
## 性能要求

系统应支持不少于1000个并发用户同时在线，响应时间不超过2秒。
```
应提取为：
- requirement: "系统需支持1000个并发用户，响应时间不超过2秒"
- original_text: "系统应支持不少于1000个并发用户同时在线，响应时间不超过2秒。"（从原文提取）
- page_number: {node.start_index}
- response_suggestion: "在技术方案中说明系统架构设计和负载均衡方案"
- risk_warning: "需要进行压力测试验证并发性能"
- notes: "关键性能指标"

**示例3：标题和原文都有需求**
```
## 系统需采用B/S架构

前端需支持Chrome、Firefox、Safari等主流浏览器，后端需支持分布式部署。
```
应提取为两条需求：
1. requirement: "系统需采用B/S架构"
   original_text: "系统需采用B/S架构"（从标题提取）
   
2. requirement: "前端支持主流浏览器，后端支持分布式部署"
   original_text: "前端需支持Chrome、Firefox、Safari等主流浏览器，后端需支持分布式部署。"（从原文提取）
"""
    return prompt
