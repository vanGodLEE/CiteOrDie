"""
PDF page dimension utilities.

Read page sizes from a PDF file and provide fallback defaults (A4)
when the file cannot be read or PyPDF2 is unavailable.
"""

from typing import Dict, List, Tuple
from pathlib import Path
from loguru import logger

# ---------------------------------------------------------------------------
# Constants – standard page sizes in PDF points (1 point = 1/72 inch)
# ---------------------------------------------------------------------------

DEFAULT_A4_WIDTH: float = 595.0
DEFAULT_A4_HEIGHT: float = 842.0
DEFAULT_FALLBACK_PAGES: int = 100

_STANDARD_PAGE_SIZES: Dict[str, Tuple[float, float]] = {
    "A4": (595.0, 842.0),
    "A3": (842.0, 1191.0),
    "Letter": (612.0, 792.0),
    "Legal": (612.0, 1008.0),
}

_SIZE_TOLERANCE: float = 5.0  # points


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_pdf_page_dimensions(pdf_path: str) -> List[Tuple[float, float]]:
    """
    Return the (width, height) in points for every page in a PDF.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of ``(width, height)`` tuples, one per page.

    Raises:
        FileNotFoundError: If *pdf_path* does not exist.
    """
    try:
        import PyPDF2

        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            dimensions = []

            for page in reader.pages:
                media_box = page.mediabox
                dimensions.append((float(media_box.width), float(media_box.height)))

            logger.debug(
                f"Read PDF dimensions: {pdf_path_obj.name}, "
                f"{len(dimensions)} page(s), "
                f"first={dimensions[0] if dimensions else 'N/A'}"
            )

            return dimensions

    except ImportError:
        logger.warning("PyPDF2 not installed, falling back to A4 defaults")
        return [(DEFAULT_A4_WIDTH, DEFAULT_A4_HEIGHT)] * DEFAULT_FALLBACK_PAGES

    except FileNotFoundError:
        raise  # let callers handle missing files explicitly

    except Exception as e:
        logger.error(f"Failed to read PDF dimensions: {e}")
        return [(DEFAULT_A4_WIDTH, DEFAULT_A4_HEIGHT)] * DEFAULT_FALLBACK_PAGES


def get_pdf_page_height(pdf_path: str, page_index: int = 0) -> float:
    """
    Return the height (in points) of a single page.

    Args:
        pdf_path: Path to the PDF file.
        page_index: Zero-based page index.

    Returns:
        Page height in points; falls back to A4 height on error.
    """
    try:
        dimensions = get_pdf_page_dimensions(pdf_path)
        if page_index < len(dimensions):
            return dimensions[page_index][1]

        logger.warning(
            f"Page index {page_index} out of range "
            f"({len(dimensions)} pages), using first page height"
        )
        return dimensions[0][1] if dimensions else DEFAULT_A4_HEIGHT
    except Exception as e:
        logger.warning(f"Failed to get page height, using A4 default: {e}")
        return DEFAULT_A4_HEIGHT


def get_average_page_height(pdf_path: str) -> float:
    """
    Return the average page height across all pages.

    Useful for documents with uniform page sizes.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Average height in points; falls back to A4 height on error.
    """
    try:
        dimensions = get_pdf_page_dimensions(pdf_path)
        if not dimensions:
            return DEFAULT_A4_HEIGHT

        heights = [h for _w, h in dimensions]
        avg_height = sum(heights) / len(heights)

        logger.debug(
            f"Average page height: {avg_height:.2f} pts "
            f"({len(heights)} page(s))"
        )

        return avg_height

    except Exception as e:
        logger.warning(f"Failed to compute average page height, using A4 default: {e}")
        return DEFAULT_A4_HEIGHT


def detect_page_size_name(width: float, height: float) -> str:
    """
    Identify the standard page size name from dimensions.

    Args:
        width: Page width in points.
        height: Page height in points.

    Returns:
        One of ``"A4"``, ``"A3"``, ``"Letter"``, ``"Legal"``, or ``"Custom"``.
    """
    for name, (std_w, std_h) in _STANDARD_PAGE_SIZES.items():
        if abs(width - std_w) < _SIZE_TOLERANCE and abs(height - std_h) < _SIZE_TOLERANCE:
            return name

    return "Custom"
