"""
Auditor节点 - 去重与汇总

负责汇总所有Worker的结果，进行简单去重
"""

from typing import List
from loguru import logger
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.core.states import TenderAnalysisState, RequirementItem
from app.core.config import settings


def auditor_node(state: TenderAnalysisState) -> dict:
    """
    Auditor节点 - 汇总和格式化（重构后：无需复杂去重）
    
    业务逻辑（重构后）：
    1. 汇总所有Worker提取的需求
    2. 可选的简单去重（基于original_text完全一致）
    3. 按章节排序
    4. 格式统一
    
    Args:
        state: 全局状态
        
    Returns:
        包含最终需求矩阵的字典
    """
    logger.info("====== Auditor节点开始执行（重构后） ======")
    
    # 更新进度：开始质检
    task_id = state.get("task_id")
    if task_id:
        from app.api.async_tasks import TaskManager
        TaskManager.update_task(task_id, progress=85, message="正在进行质量检查和汇总...")
    
    requirements = state.get("requirements", [])
    
    if not requirements:
        logger.warning("没有提取到任何需求")
        return {"final_matrix": []}
    
    logger.info(f"开始处理 {len(requirements)} 条原始需求")
    
    # 步骤1: 简单去重（可选，仅去除完全相同的需求）
    deduplicated = _simple_deduplicate_requirements(requirements)
    if len(deduplicated) < len(requirements):
        logger.info(f"简单去重后剩余 {len(deduplicated)} 条需求（去除了 {len(requirements) - len(deduplicated)} 条完全重复）")
    
    # 步骤2: 按章节排序
    sorted_reqs = _sort_requirements(deduplicated)
    
    # 步骤3: 格式统一
    final_matrix = _normalize_requirements(sorted_reqs)
    
    logger.info(f"====== Auditor完成，最终输出 {len(final_matrix)} 条需求 ======")
    _print_summary(final_matrix)
    
    return {"final_matrix": final_matrix}


def _simple_deduplicate_requirements(requirements: List[RequirementItem]) -> List[RequirementItem]:
    """
    简单去重：仅去除original_text完全相同的需求
    
    重构后说明：
    - 由于使用了精确原文填充，理论上不应该有重复需求
    - 此函数仅作为保险措施，去除万一出现的完全重复项
    - 不再使用复杂的TF-IDF相似度计算
    """
    if len(requirements) <= 1:
        return requirements
    
    try:
        seen_texts = set()
        deduplicated = []
        removed_count = 0
        
        for req in requirements:
            # 使用original_text作为去重依据
            text_key = req.original_text.strip()
            
            if text_key not in seen_texts:
                seen_texts.add(text_key)
                deduplicated.append(req)
            else:
                removed_count += 1
                logger.debug(f"去重：移除完全重复需求 {req.matrix_id}")
        
        if removed_count > 0:
            logger.info(f"简单去重移除了 {removed_count} 条完全重复的需求")
        
        return deduplicated
        
    except Exception as e:
        logger.warning(f"简单去重过程出错，返回原始列表: {e}")
        return requirements


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
