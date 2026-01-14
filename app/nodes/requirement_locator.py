"""
Requirement Locator节点 - 为需求定位positions

遍历所有节点的requirements，为每个需求填充positions字段：
- 图片/表格需求 → 直接使用节点的positions
- 文本需求 → 使用RequirementTextMatcher智能匹配
"""

from typing import Dict, Any, List
from loguru import logger
from app.core.states import TenderAnalysisState, PageIndexNode, RequirementItem
from app.utils.requirement_matcher import RequirementTextMatcher, extract_node_content_list


def requirement_locator_node(state: TenderAnalysisState) -> Dict[str, Any]:
    """
    需求位置定位节点
    
    输入：
    - state.pageindex_document: 包含所有节点和需求的文档树
    - state.mineru_content_list: MinerU解析的完整content_list
    
    输出：
    - 更新所有requirement的positions字段（通过引用直接修改）
    
    工作流程：
    1. 遍历所有节点的requirements
    2. 判断需求来源（图片/表格 vs 文本）
    3. 图片/表格需求 → 直接使用节点positions
    4. 文本需求 → 使用RequirementTextMatcher智能匹配
    5. 填充positions字段
    """
    logger.info("=" * 60)
    logger.info("需求位置定位节点开始执行")
    logger.info("=" * 60)
    
    pageindex_doc = state.get("pageindex_document")
    mineru_content_list = state.get("mineru_content_list", [])
    
    if not pageindex_doc:
        logger.warning("未找到pageindex_document，跳过位置定位")
        return {}
    
    if not mineru_content_list:
        logger.warning("未找到mineru_content_list，跳过位置定位")
        return {}
    
    # 统计信息
    total_requirements = 0
    visual_requirements = 0  # 图片/表格需求
    text_requirements = 0    # 文本需求
    located_requirements = 0
    failed_requirements = 0
    
    # 遍历所有节点
    for root_node in pageindex_doc.structure:
        all_nodes = root_node.get_all_nodes()
        
        for node in all_nodes:
            if not node.requirements:
                continue
            
            logger.info(f"处理节点 '{node.title}' 的 {len(node.requirements)} 个需求")
            
            # 为每个需求定位positions
            for req in node.requirements:
                total_requirements += 1
                
                # 判断需求来源
                is_visual = bool(req.image_caption or req.table_caption)
                
                if is_visual:
                    # 图片/表格需求 → 精确定位到表格或使用节点positions
                    visual_requirements += 1
                    positions = _locate_visual_requirement(
                        req,
                        node,
                        mineru_content_list
                    )
                    logger.debug(
                        f"  [图片/表格] {req.matrix_id}: "
                        f"匹配到 {len(positions)} 个bbox"
                    )
                else:
                    # 文本需求 → 智能匹配
                    text_requirements += 1
                    positions = _locate_text_requirement(
                        req, 
                        node, 
                        mineru_content_list
                    )
                    logger.debug(
                        f"  [文本] {req.matrix_id}: "
                        f"匹配到 {len(positions)} 个bbox"
                    )
                
                # 填充positions
                if positions:
                    req.positions = positions
                    located_requirements += 1
                else:
                    req.positions = []
                    failed_requirements += 1
                    logger.warning(
                        f"  ❌ 需求定位失败: {req.matrix_id}\n"
                        f"     需求概述: {req.requirement[:50]}...\n"
                        f"     原文片段: {req.original_text[:50]}..."
                    )
    
    # 输出统计
    logger.info(f"✓ 需求位置定位完成")
    logger.info(f"  - 总需求数: {total_requirements}")
    logger.info(f"  - 图片/表格需求: {visual_requirements}")
    logger.info(f"  - 文本需求: {text_requirements}")
    logger.info(f"  - 定位成功: {located_requirements}")
    logger.info(f"  - 定位失败: {failed_requirements}")
    
    if total_requirements > 0:
        success_rate = located_requirements / total_requirements * 100
        logger.info(f"  - 成功率: {success_rate:.1f}%")
        
        if success_rate < 95:
            logger.warning(
                f"⚠️  定位成功率偏低 ({success_rate:.1f}%)，"
                f"请检查文本匹配算法"
            )
    
    # 不修改state（需求已通过引用更新）
    return {}


def _locate_visual_requirement(
    requirement: RequirementItem,
    node: PageIndexNode,
    mineru_content_list: List[Dict[str, Any]]
) -> List[List[int]]:
    """
    定位图片/表格需求的positions（✅ 优化：基于img_path精确匹配）
    
    策略（按优先级）：
    1. **精确匹配**：如果requirement有img_path → 直接在content_list中查找对应content
    2. **表格兜底**：如果是表格且无img_path → 尝试在节点范围内查找第一个表格
    3. **节点兜底**：使用节点的所有positions
    
    Args:
        requirement: 需求对象（可能包含img_path字段）
        node: 节点对象
        mineru_content_list: MinerU完整content列表
    
    Returns:
        positions列表
    """
    # ✅ 策略1：img_path精确匹配（最高优先级）
    if requirement.img_path:
        positions = _find_content_by_img_path(
            requirement.img_path,
            mineru_content_list
        )
        if positions:
            logger.debug(
                f"✓ 图片/表格需求 {requirement.matrix_id}: "
                f"通过img_path精确匹配 ({requirement.img_path})"
            )
            return positions
        else:
            logger.warning(
                f"⚠️  需求 {requirement.matrix_id} 的img_path={requirement.img_path} "
                f"在content_list中未找到，尝试兜底策略"
            )
    
    # 策略2：表格兜底（仅在无img_path时）
    if requirement.table_caption and not requirement.img_path:
        table_positions = _find_table_positions(node, mineru_content_list)
        if table_positions:
            logger.debug(
                f"✓ 表格需求 {requirement.matrix_id}: "
                f"在节点范围内找到表格bbox ({len(table_positions)} 个)"
            )
            return table_positions
    
    # 策略3：节点兜底（最后手段）
    if node.positions:
        logger.debug(
            f"使用节点兜底: 需求 {requirement.matrix_id} → "
            f"节点 '{node.title}' 的 {len(node.positions)} 个bbox"
        )
        return node.positions.copy()
    else:
        logger.warning(
            f"❌ 需求 {requirement.matrix_id}: "
            f"所有匹配策略失败，节点 '{node.title}' 的positions也为空"
        )
        return []


def _find_content_by_img_path(
    img_path: str,
    mineru_content_list: List[Dict[str, Any]]
) -> List[List[int]]:
    """
    ✅ 新增：基于img_path精确查找content的positions
    
    策略：
    1. 遍历content_list，查找img_path匹配的content
    2. 返回该content的bbox位置
    
    Args:
        img_path: 图片/表格的相对路径（如"images/xxx.jpg"）
        mineru_content_list: MinerU完整content列表
    
    Returns:
        positions列表（单个bbox）
    """
    for content in mineru_content_list:
        content_img_path = content.get("img_path", "")
        
        # 精确匹配img_path
        if content_img_path == img_path:
            bbox = content.get("bbox")
            page_idx = content.get("page_idx")
            content_type = content.get("type", "unknown")
            
            if bbox and page_idx is not None and len(bbox) == 4:
                position = [page_idx] + bbox
                logger.debug(
                    f"✓ img_path精确匹配: {img_path} → "
                    f"type={content_type}, page={page_idx}, bbox={bbox}"
                )
                return [position]
            else:
                logger.warning(
                    f"⚠️  找到img_path={img_path}，但bbox格式错误: "
                    f"bbox={bbox}, page_idx={page_idx}"
                )
                return []
    
    logger.warning(f"❌ 未找到img_path={img_path}的content")
    return []


def _find_table_positions(
    node: PageIndexNode,
    mineru_content_list: List[Dict[str, Any]]
) -> List[List[int]]:
    """
    在content_list中查找节点对应的表格positions（兜底策略）
    
    策略：
    1. 提取节点对应的content_list
    2. 找到type="table"的content
    3. 返回第一个表格的bbox（如果有多个表格，返回第一个）
    
    Args:
        node: 节点对象
        mineru_content_list: MinerU完整content列表
    
    Returns:
        表格的positions列表
    """
    # 提取节点对应的content_list
    node_content_list = extract_node_content_list(
        node_positions=node.positions,
        full_content_list=mineru_content_list
    )
    
    # 查找type="table"的content
    for content in node_content_list:
        if content.get("type") == "table":
            bbox = content.get("bbox")
            page_idx = content.get("page_idx")
            
            if bbox and page_idx is not None:
                # 构建position: [page_idx, x1, y1, x2, y2]
                if len(bbox) == 4:
                    position = [page_idx] + bbox
                    logger.debug(
                        f"找到表格: page={page_idx}, bbox={bbox}, "
                        f"img_path={content.get('img_path', 'N/A')[:50]}..."
                    )
                    return [position]
    
    logger.debug(f"节点 '{node.title}' 中未找到表格content")
    return []


def _locate_text_requirement(
    requirement: RequirementItem,
    node: PageIndexNode,
    mineru_content_list: List[Dict[str, Any]]
) -> List[List[int]]:
    """
    定位文本需求的positions
    
    策略：使用RequirementTextMatcher智能匹配
    
    Args:
        requirement: 需求对象
        node: 节点对象
        mineru_content_list: MinerU完整content列表
    
    Returns:
        positions列表
    """
    # 1. 提取节点对应的content_list（缩小搜索范围）
    node_content_list = extract_node_content_list(
        node_positions=node.positions,
        full_content_list=mineru_content_list
    )
    
    if not node_content_list:
        logger.warning(
            f"节点 '{node.title}' 的content_list为空，"
            f"无法为需求 {requirement.matrix_id} 定位positions"
        )
        return []
    
    # 2. 使用RequirementTextMatcher进行智能匹配
    positions = RequirementTextMatcher.find_requirement_positions(
        requirement_text=requirement.original_text,
        node_content_list=node_content_list,
        node_positions=node.positions
    )
    
    return positions