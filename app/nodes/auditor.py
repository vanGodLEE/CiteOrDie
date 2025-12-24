"""
Auditor节点 - 汇总与格式化

负责汇总所有Worker的结果（不去重）
"""

from typing import List
from loguru import logger

from app.core.states import TenderAnalysisState, RequirementItem
from app.core.config import settings


def auditor_node(state: TenderAnalysisState) -> dict:
    """
    Auditor节点 - 汇总和格式化（不去重版本）
    
    业务逻辑：
    1. 汇总所有Worker提取的需求
    2. 按章节排序
    3. 格式统一
    
    注意：不进行去重！
    - 不同章节可能包含相同的需求描述
    - 去重会导致某些章节的需求信息丢失
    - 保留所有需求，即使内容相同，因为它们来自不同的章节上下文
    
    Args:
        state: 全局状态
        
    Returns:
        包含最终需求矩阵的字典
    """
    logger.info("====== Auditor节点开始执行（不去重版本） ======")
    
    # 更新进度：开始质检
    task_id = state.get("task_id")
    if task_id:
        from app.api.async_tasks import TaskManager
        TaskManager.update_task(task_id, progress=85, message="正在进行质量检查和汇总...")
    
    requirements = state.get("requirements", [])
    
    if not requirements:
        logger.warning("没有提取到任何需求")
        return {"final_matrix": []}
    
    logger.info(f"开始处理 {len(requirements)} 条原始需求（不去重）")
    
    # 步骤1: 按章节排序（不去重）
    sorted_reqs = _sort_requirements(requirements)
    
    # 步骤2: 格式统一
    final_matrix = _normalize_requirements(sorted_reqs)
    
    logger.info(f"====== Auditor完成，最终输出 {len(final_matrix)} 条需求 ======")
    _print_summary(final_matrix)
    
    return {"final_matrix": final_matrix}


def _sort_requirements(requirements: List[RequirementItem]) -> List[RequirementItem]:
    """
    排序需求：按章节编号和matrix_id排序
    """
    sorted_reqs = sorted(
        requirements,
        key=lambda x: (x.section_id, x.matrix_id)
    )
    
    return sorted_reqs


def _normalize_requirements(requirements: List[RequirementItem]) -> List[RequirementItem]:
    """
    格式统一：去除多余空格
    """
    for req in requirements:
        req.requirement = req.requirement.strip()
        req.original_text = req.original_text.strip()
        req.section_title = req.section_title.strip()
        req.response_suggestion = req.response_suggestion.strip()
        req.risk_warning = req.risk_warning.strip()
        req.notes = req.notes.strip()
    
    return requirements


def _print_summary(requirements: List[RequirementItem]):
    """打印需求摘要统计"""
    # 按章节统计
    section_stats = {}
    for req in requirements:
        section_key = f"{req.section_id} {req.section_title}"
        section_stats[section_key] = section_stats.get(section_key, 0) + 1
    
    logger.info(f"需求统计：")
    logger.info(f"  - 总计: {len(requirements)} 条需求")
    logger.info(f"  - 涉及章节: {len(section_stats)} 个")
    
    # 显示前5个章节的需求数
    sorted_sections = sorted(section_stats.items(), key=lambda x: x[1], reverse=True)
    logger.info(f"  需求最多的章节（前5）：")
    for section, count in sorted_sections[:5]:
        logger.info(f"    - {section}: {count} 条")
