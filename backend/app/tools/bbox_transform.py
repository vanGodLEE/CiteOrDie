"""
Bounding-box coordinate transformation (PDF-native ↔ frontend).

PDF-native coordinate system (origin at bottom-left, Y-axis up)
  →  Frontend / PDF.js coordinate system (origin at top-left, Y-axis down).

The conversion flips Y values:  y_new = page_height - y_old,
and swaps y1/y2 so that the resulting bbox is [x1, y_top, x2, y_bottom].
"""

from typing import List
from loguru import logger


def convert_bbox_to_frontend(
    bbox: List[float],
    page_height: float,
) -> List[int]:
    """
    Flip a single bbox from PDF-native coords to frontend coords.

    PDF-native (bottom-left origin):
        bbox = [x1, y1, x2, y2]
        (x1, y1) = bottom-left of the text block
        (x2, y2) = top-right of the text block

    Frontend / PDF.js (top-left origin):
        bbox = [x1, y1, x2, y2]
        (x1, y1) = top-left of the text block
        (x2, y2) = bottom-right of the text block

    Args:
        bbox: Four-element list ``[x1, y1, x2, y2]`` in PDF-native coords.
        page_height: Page height in points.

    Returns:
        Four-element integer list ``[x1, y1, x2, y2]`` in frontend coords.

    Example:
        >>> convert_bbox_to_frontend([100, 500, 300, 520], 800)
        [100, 280, 300, 300]
    """
    if len(bbox) != 4:
        logger.warning(f"Invalid bbox (expected 4 elements): {bbox}")
        return [0, 0, 0, 0]

    x1, y1, x2, y2 = bbox

    # Flip Y-axis: PDF y2 (top) → frontend y1 (top), PDF y1 (bottom) → frontend y2 (bottom)
    y1_new = page_height - y2
    y2_new = page_height - y1

    # Round to integers (avoids Pydantic validation errors downstream)
    return [round(x1), round(y1_new), round(x2), round(y2_new)]


def convert_position_to_frontend(
    position: List,
    page_height: float,
) -> List[int]:
    """
    Flip a single position (with page index) from PDF-native to frontend coords.

    Args:
        position: Five-element list ``[page_idx, x1, y1, x2, y2]``.
        page_height: Page height in points.

    Returns:
        ``[page_idx, x1, y1, x2, y2]`` as integers in frontend coords.
    """
    if len(position) != 5:
        logger.warning(f"Invalid position (expected 5 elements): {position}")
        return [0, 0, 0, 0, 0]

    page_idx = position[0]
    bbox = position[1:5]

    converted_bbox = convert_bbox_to_frontend(bbox, page_height)
    return [int(page_idx)] + converted_bbox


def convert_positions_to_frontend(
    positions: List[List],
    page_height: float,
) -> List[List[int]]:
    """
    Batch-convert a list of positions from PDF-native to frontend coords.

    Args:
        positions: List of ``[page_idx, x1, y1, x2, y2]`` entries.
        page_height: Page height in points.

    Returns:
        Converted positions as integer lists.
    """
    return [convert_position_to_frontend(pos, page_height) for pos in positions]
