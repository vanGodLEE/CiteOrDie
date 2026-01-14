"""
坐标系转换工具

MinerU使用PDF原生坐标系（原点在左下角，Y轴向上）
前端PDF.js使用浏览器坐标系（原点在左上角，Y轴向下）

需要进行坐标转换
"""

from typing import List
from loguru import logger


def convert_bbox_to_frontend(
    bbox: List[float],
    page_height: float
) -> List[int]:
    """
    将MinerU的bbox转换为前端PDF.js所需的坐标系
    
    MinerU坐标系（左下角原点）:
        - 原点: 左下角
        - Y轴方向: 向上（底部=0，顶部=page_height）
        - bbox格式: [x1, y1, x2, y2]
          - (x1, y1): 文本框的左下角
          - (x2, y2): 文本框的右上角
    
    前端PDF.js坐标系（左上角原点）:
        - 原点: 左上角
        - Y轴方向: 向下（顶部=0，底部=page_height）
        - bbox格式: [x1, y1, x2, y2]
          - (x1, y1): 文本框的左上角
          - (x2, y2): 文本框的右下角
    
    转换规则:
        - X坐标保持不变
        - Y坐标转换: y_new = page_height - y_old
        - 注意y1和y2的位置互换
        - 所有坐标四舍五入为整数
    
    Args:
        bbox: MinerU的bbox [x1, y1, x2, y2]
        page_height: PDF页面高度（单位：points）
    
    Returns:
        转换后的bbox [x1, y1, x2, y2]（整数）
    
    Example:
        # 假设页面高度为800
        >>> bbox_mineru = [100, 500, 300, 520]  # y1=500在底部，y2=520在顶部
        >>> convert_bbox_to_frontend(bbox_mineru, 800)
        [100, 280, 300, 300]  # y1=280在顶部，y2=300在底部
    """
    if len(bbox) != 4:
        logger.warning(f"无效的bbox格式: {bbox}，应该是4个元素")
        return [0, 0, 0, 0]
    
    x1, y1, x2, y2 = bbox
    
    # 转换Y坐标
    # MinerU: y1是底部，y2是顶部
    # 前端: y1应该是顶部，y2应该是底部
    y1_new = page_height - y2  # MinerU的y2（顶部）→ 前端的y1（顶部）
    y2_new = page_height - y1  # MinerU的y1（底部）→ 前端的y2（底部）
    
    # ✅ 四舍五入为整数（避免Pydantic验证错误）
    return [
        round(x1),
        round(y1_new),
        round(x2),
        round(y2_new)
    ]


def convert_position_to_frontend(
    position: List,
    page_height: float
) -> List[int]:
    """
    转换position格式的坐标（包含page_idx）
    
    Args:
        position: [page_idx, x1, y1, x2, y2]
        page_height: PDF页面高度
    
    Returns:
        转换后的position [page_idx, x1, y1, x2, y2]（整数）
    """
    if len(position) != 5:
        logger.warning(f"无效的position格式: {position}，应该是5个元素")
        return [0, 0, 0, 0, 0]
    
    page_idx = position[0]
    bbox = position[1:5]
    
    # 转换bbox（已经是整数）
    converted_bbox = convert_bbox_to_frontend(bbox, page_height)
    
    return [int(page_idx)] + converted_bbox


def convert_positions_to_frontend(
    positions: List[List],
    page_height: float
) -> List[List[int]]:
    """
    批量转换positions
    
    Args:
        positions: [[page_idx, x1, y1, x2, y2], ...]
        page_height: PDF页面高度
    
    Returns:
        转换后的positions（整数）
    """
    return [
        convert_position_to_frontend(pos, page_height)
        for pos in positions
    ]


# 标准页面尺寸（单位：points，1 point = 1/72 inch）
PAGE_SIZES = {
    "A4": (595.0, 842.0),      # 210mm × 297mm
    "A3": (842.0, 1191.0),     # 297mm × 420mm
    "Letter": (612.0, 792.0),  # 8.5in × 11in
    "Legal": (612.0, 1008.0),  # 8.5in × 14in
}


def get_page_height(page_size: str = "A4") -> float:
    """
    获取标准页面高度
    
    Args:
        page_size: 页面尺寸名称（A4/A3/Letter/Legal）
    
    Returns:
        页面高度（points）
    """
    if page_size in PAGE_SIZES:
        return PAGE_SIZES[page_size][1]
    
    logger.warning(f"未知的页面尺寸: {page_size}，使用A4默认值")
    return 842.0  # A4高度