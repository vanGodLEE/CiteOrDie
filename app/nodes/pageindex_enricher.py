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
    构建需求提取的提示词（智能版：处理标题中的需求 + 类型分类）
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

**提取来源判断**：
- 标题包含明确需求 → 从标题提取，original_text填写标题内容
- 标题仅是分类 → 从原文提取，original_text填写原文内容
- 标题和原文都有需求 → 分别提取，各自记录original_text

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
"""
    return prompt
