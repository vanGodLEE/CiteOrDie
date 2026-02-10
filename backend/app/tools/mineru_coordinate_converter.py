"""
MinerU normalized-coordinate converter.

MinerU produces bounding boxes in a 0-1000 normalized coordinate system
(origin at top-left, Y-axis pointing down).  This module scales those
values to actual PDF page coordinates (in points) so the frontend can
render highlights directly on a canvas without further transformation.

Page dimensions are obtained via *pdfplumber* for consistency with the
upstream parsing pipeline.
"""

from typing import List, Tuple

import pdfplumber
from loguru import logger

from app.tools.pdf_page_info import DEFAULT_A4_WIDTH, DEFAULT_A4_HEIGHT

# MinerU bbox values are normalized to this range.
MINERU_NORM_RANGE: float = 1000.0


# ---------------------------------------------------------------------------
# Single-bbox conversion
# ---------------------------------------------------------------------------

def convert_mineru_to_page_rect(
    bbox: List[int],
    page_width: float,
    page_height: float,
) -> List[float]:
    """
    Scale a MinerU normalized bbox to actual page coordinates.

    No Y-axis flip is needed because both MinerU and the frontend canvas
    share a top-left origin with Y pointing downward.

    Args:
        bbox: ``[x0, y0, x1, y1]`` in the 0-1000 normalized range.
        page_width: Page width in points.
        page_height: Page height in points.

    Returns:
        ``[x0, y0, x1, y1]`` in points (top-left origin).

    Example:
        >>> convert_mineru_to_page_rect([213, 253, 784, 317], 612, 792)
        [130.356, 200.376, 479.808, 251.064]
    """
    x0_norm, y0_norm, x1_norm, y1_norm = bbox

    # Scale normalized coords to actual page coords (origin stays top-left)
    x0 = (x0_norm / MINERU_NORM_RANGE) * page_width
    x1 = (x1_norm / MINERU_NORM_RANGE) * page_width
    y0 = (y0_norm / MINERU_NORM_RANGE) * page_height
    y1 = (y1_norm / MINERU_NORM_RANGE) * page_height

    return [x0, y0, x1, y1]


# ---------------------------------------------------------------------------
# Batch conversion
# ---------------------------------------------------------------------------

def convert_positions_for_frontend(
    positions: List[List[int]],
    pdf_path: str = None,
    page_dimensions: List[Tuple[float, float]] = None,
) -> List[List[float]]:
    """
    Batch-convert MinerU positions to page coordinates (top-left origin).

    Either *pdf_path* or *page_dimensions* must be supplied.  Passing
    pre-fetched *page_dimensions* avoids repeatedly opening the PDF.

    Args:
        positions: ``[[page_idx, x0, y0, x1, y1], ...]``
            (0-based page index, 0-1000 normalized coords).
        pdf_path: Path to the PDF (used when *page_dimensions* is ``None``).
        page_dimensions: Pre-fetched ``[(width, height), ...]`` per page.

    Returns:
        ``[[page_idx, x0, y0, x1, y1], ...]`` in points (top-left origin).

    Raises:
        ValueError: If neither *pdf_path* nor *page_dimensions* is provided.
    """
    if not positions:
        return []

    # Resolve page dimensions -------------------------------------------------
    if page_dimensions is None:
        if pdf_path is None:
            raise ValueError("Either pdf_path or page_dimensions must be provided")

        with pdfplumber.open(pdf_path) as pdf:
            page_dimensions = [(page.width, page.height) for page in pdf.pages]
            logger.info(
                f"[CoordConvert] Read {len(page_dimensions)} page dimensions via pdfplumber"
            )
            for i, (w, h) in enumerate(page_dimensions[:3]):
                logger.debug(f"[CoordConvert] Page {i}: {w:.1f} x {h:.1f} pts")
    else:
        logger.debug(
            f"[CoordConvert] Using cached dimensions ({len(page_dimensions)} pages)"
        )

    # Convert each position ----------------------------------------------------
    converted: List[List[float]] = []
    for pos in positions:
        page_idx, x0, y0, x1, y1 = pos

        if page_idx < len(page_dimensions):
            page_width, page_height = page_dimensions[page_idx]
        else:
            logger.warning(
                f"[CoordConvert] Page index {page_idx} out of range, using A4 defaults"
            )
            page_width, page_height = DEFAULT_A4_WIDTH, DEFAULT_A4_HEIGHT

        page_rect = convert_mineru_to_page_rect(
            [x0, y0, x1, y1], page_width, page_height,
        )
        converted.append([page_idx] + page_rect)

    return converted


# ---------------------------------------------------------------------------
# Page-dimension helpers (via pdfplumber)
# ---------------------------------------------------------------------------

def get_page_dimensions(pdf_path: str, page_idx: int) -> Tuple[float, float]:
    """
    Return ``(width, height)`` in points for a single page.

    Args:
        pdf_path: Path to the PDF file.
        page_idx: Zero-based page index.

    Returns:
        ``(width, height)`` in points; A4 defaults if *page_idx* is out of range.
    """
    with pdfplumber.open(pdf_path) as pdf:
        if page_idx < len(pdf.pages):
            page = pdf.pages[page_idx]
            return page.width, page.height

        logger.warning(
            f"[CoordConvert] Page index {page_idx} out of range, returning A4 defaults"
        )
        return DEFAULT_A4_WIDTH, DEFAULT_A4_HEIGHT


def get_all_page_dimensions(pdf_path: str) -> List[Tuple[float, float]]:
    """
    Return ``[(width, height), ...]`` for every page (cacheable).

    Intended for callers that need to convert many positions – fetch once,
    then pass the result to :func:`convert_positions_for_frontend`.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of ``(width, height)`` tuples, one per page.
    """
    with pdfplumber.open(pdf_path) as pdf:
        dims = [(page.width, page.height) for page in pdf.pages]
        logger.info(f"[CoordConvert] Cached dimensions for {len(dims)} pages")
        return dims