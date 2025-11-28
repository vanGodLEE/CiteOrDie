"""
Extractor节点 - 并行需求提取Worker

每个Worker负责分析一个章节，提取所有需求条款
这是系统的"人海战术"
"""

from typing import List
from pydantic import BaseModel
from loguru import logger

from app.core.states import SectionState, RequirementItem, ContentBlock, create_matrix_id
from app.services.llm_service import llm_service


# Pydantic模型用于Structured Output
class RequirementList(BaseModel):
    """需求列表"""
    requirements: List[RequirementItem]


def extractor_node(state: SectionState) -> dict:
    """
    Extractor节点 - 需求提取Worker
    
    业务逻辑：
    1. 接收一个章节的内容
    2. 使用LLM识别所有需求条款
    3. 对每个需求判断重要性级别（CRITICAL/SCORING/NORMAL）
    4. 提取原文作为证据
    5. 生成唯一的matrix_id
    
    Args:
        state: 章节状态（SectionState）
        
    Returns:
        包含需求列表的字典
    """
    section_id = state["section_id"]
    section_title = state["section_title"]
    content_blocks = state["content_blocks"]
    task_id = state.get("task_id")
    
    logger.info(f"====== Extractor开始处理章节: {section_id} {section_title} ======")
    
    # 更新进度：开始提取某个章节
    if task_id:
        from app.api.async_tasks import TaskManager
        TaskManager.update_task(task_id, progress=40, message=f"正在提取章节需求: {section_title[:30]}...")
    logger.debug(f"章节包含 {len(content_blocks)} 个内容块")
    
    # 将内容块转换为文本
    section_text = _format_content_blocks(content_blocks)
    logger.debug(f"章节文本长度: {len(section_text)} 字符")
    logger.debug(f"章节文本预览: {section_text[:200]}...")
    
    # 构造Prompt
    system_prompt = """你是软件项目招标分析专家。你的任务是从章节内容中提取**软件行业的技术需求**。

## ⚠️ 核心原则：这是软件项目招标，只提取技术需求

### ✅ 应该提取的需求（软件项目的技术需求）
- **软件功能**（如：用户管理、数据导入、报表生成、工作流引擎）
- **性能指标**（如：响应时间<2秒、支持1000并发用户）
- **接口规范**（如：提供RESTful API、对接第三方系统）
- **安全要求**（如：数据加密、权限控制、等保三级）
- **技术架构**（如：微服务架构、前后端分离）
- **数据要求**（如：数据库类型、数据迁移）
- **运行环境**（如：服务器配置、操作系统、数据库版本）
- **兼容性**（如：支持Chrome/Firefox、移动端适配）
- **开发规范**（如：代码规范、文档要求）

### ❌ 应该过滤的内容（不提取）
- 商务资质（营业执照、企业资质、业绩证明）
- 纯硬件采购（采购交换机、存储设备）
- 合同条款（付款方式、违约责任）
- 服务方案（培训计划、质保期限）

## 输出字段说明

提取每个需求后，需要填写以下字段：

1. **requirement**（需求）：用一句话概括需求内容，清晰简洁
2. **original_text**（原文）：从章节中精确摘录的原文，不要改写
3. **page_number**（页码）：从content_block中获取
4. **response_suggestion**（应答方向）：给投标人一个简短建议，如何响应这个需求
5. **risk_warning**（风险提示）：这个需求可能有什么坑或风险，给个提示
6. **notes**（备注）：其他补充说明

注意：
- matrix_id、section_id、section_title由系统自动填充，不需要生成
- 如果整个章节没有软件技术需求，返回空列表
- 不要合并多个需求，每个需求单独一条
"""
    
    user_prompt = f"""请分析以下章节内容，提取所有需求条款：

章节：{section_id} {section_title}

内容：
{section_text}

请按照规则提取需求，每个需求必须包含完整的字段信息。
注意：matrix_id字段请留空，将由系统自动生成。
"""
    
    # 调用LLM进行结构化输出
    try:
        result = llm_service.structured_completion(
            messages=[
                llm_service.create_system_message(system_prompt),
                llm_service.create_user_message(user_prompt)
            ],
            response_model=RequirementList,
            temperature=0.1
        )
        
        requirements = result.requirements
        
        # 后处理：生成matrix_id
        for i, req in enumerate(requirements, start=1):
            if not req.matrix_id or req.matrix_id == "":
                req.matrix_id = create_matrix_id(section_id, i)
        
        logger.info(f"章节 {section_id} 提取到 {len(requirements)} 条需求")
        
        # 显示前3个需求预览
        for i, req in enumerate(requirements[:3]):
            logger.debug(f"  需求{i+1}: {req.requirement[:60]}...")
        
        # 返回结果（会被LangGraph追加到全局state的requirements中）
        return {"requirements": requirements}
        
    except Exception as e:
        logger.error(f"Extractor处理章节 {section_id} 失败: {e}")
        # 返回空列表而不是抛出异常，避免影响其他Worker
        return {"requirements": []}


def _format_content_blocks(content_blocks: List[ContentBlock]) -> str:
    """
    将内容块格式化为LLM易读的文本
    
    包含页码信息，便于后续溯源
    """
    lines = []
    
    for block in content_blocks:
        page_num = block.page_idx + 1
        
        if block.type == "header":
            lines.append(f"\n### {block.text} (第{page_num}页)")
        elif block.type == "text":
            lines.append(f"{block.text} (第{page_num}页)")
        elif block.type == "table":
            lines.append(f"\n表格 (第{page_num}页):\n{block.text}\n")
        elif block.type == "image":
            lines.append(f"[图片] (第{page_num}页)")
        
        lines.append("")  # 空行
    
    return "\n".join(lines)
