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
    Auditor节点 - 去重和汇总
    
    业务逻辑：
    1. 汇总所有Worker提取的需求
    2. 去重：使用文本相似度检测重复需求
    3. 按章节排序
    
    Args:
        state: 全局状态
        
    Returns:
        包含最终需求矩阵的字典
    """
    logger.info("====== Auditor节点开始执行 ======")
    
    # 更新进度：开始质检去重
    task_id = state.get("task_id")
    if task_id:
        from app.api.async_tasks import TaskManager
        TaskManager.update_task(task_id, progress=85, message="正在进行质量检查和去重...")
    
    requirements = state.get("requirements", [])
    
    if not requirements:
        logger.warning("没有提取到任何需求")
        return {"final_matrix": []}
    
    logger.info(f"开始处理 {len(requirements)} 条原始需求")
    
    # 步骤1: 去重
    deduplicated = _deduplicate_requirements(requirements)
    logger.info(f"去重后剩余 {len(deduplicated)} 条需求")
    
    # 步骤2: 按章节排序
    sorted_reqs = _sort_requirements(deduplicated)
    
    # 步骤3: 格式统一
    final_matrix = _normalize_requirements(sorted_reqs)
    
    logger.info(f"====== Auditor完成，最终输出 {len(final_matrix)} 条需求 ======")
    _print_summary(final_matrix)
    
    return {"final_matrix": final_matrix}


def _deduplicate_requirements(requirements: List[RequirementItem]) -> List[RequirementItem]:
    """
    去重：使用TF-IDF + Cosine Similarity检测相似需求
    
    如果两个需求的相似度超过阈值，保留第一个
    """
    if len(requirements) <= 1:
        return requirements
    
    try:
        # 提取文本用于相似度计算（使用requirement + original_text的组合）
        texts = [f"{req.requirement} {req.original_text}" for req in requirements]
        
        # 计算TF-IDF向量
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(texts)
        
        # 计算余弦相似度
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # 标记要保留的需求
        to_keep = [True] * len(requirements)
        similarity_threshold = settings.similarity_threshold
        
        for i in range(len(requirements)):
            if not to_keep[i]:
                continue
            
            for j in range(i + 1, len(requirements)):
                if not to_keep[j]:
                    continue
                
                # 如果相似度超过阈值，保留第一个
                if similarity_matrix[i, j] >= similarity_threshold:
                        to_keep[j] = False
                        logger.debug(f"去重：移除相似需求 {requirements[j].matrix_id}")
        
        deduplicated = [req for i, req in enumerate(requirements) if to_keep[i]]
        removed_count = len(requirements) - len(deduplicated)
        if removed_count > 0:
            logger.info(f"去重移除了 {removed_count} 条相似需求")
        
        return deduplicated
        
    except Exception as e:
        logger.warning(f"去重过程出错，返回原始列表: {e}")
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
