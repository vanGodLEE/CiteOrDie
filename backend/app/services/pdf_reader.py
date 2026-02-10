"""
PDF text reader (PyMuPDF wrapper).

Extracts plain text from PDF pages, supporting single-page, multi-page,
and page-count queries.  Intended for the text-filler node that populates
``original_text`` on document-tree nodes.
"""

from typing import List

import fitz  # PyMuPDF
from loguru import logger


class PDFReader:
    """
    Context-managed PDF text reader backed by PyMuPDF.

    Usage::

        with PDFReader("doc.pdf") as reader:
            text = reader.extract_page_text(1)
    """

    def __init__(self, pdf_path: str) -> None:
        """
        Args:
            pdf_path: Path to the PDF file.
        """
        self.pdf_path = pdf_path
        self._doc: fitz.Document | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "PDFReader":
        self._doc = fitz.open(self.pdf_path)
        logger.debug(f"Opened PDF: {self.pdf_path} ({len(self._doc)} pages)")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        if self._doc:
            self._doc.close()
            self._doc = None

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _ensure_open(self) -> None:
        """Raise if the document has not been opened via ``with``."""
        if not self._doc:
            raise RuntimeError(
                "PDF document is not open. Use the 'with' statement."
            )

    def extract_page_text(self, page_num: int) -> str:
        """
        Extract text from a single page.

        Args:
            page_num: 1-based page number.

        Returns:
            Page text, or an empty string on failure / out-of-range.
        """
        self._ensure_open()

        if page_num < 1 or page_num > len(self._doc):
            logger.warning(
                f"Page {page_num} out of range [1, {len(self._doc)}]"
            )
            return ""

        try:
            page = self._doc[page_num - 1]
            text = page.get_text()
            logger.debug(f"Extracted page {page_num} text (length={len(text)})")
            return text
        except Exception as e:
            logger.error(f"Failed to extract text from page {page_num}: {e}")
            return ""

    def extract_pages_text(
        self,
        start_page: int,
        end_page: int,
        add_page_markers: bool = True,
    ) -> str:
        """
        Extract and concatenate text from a page range.

        Args:
            start_page: First page (1-based, inclusive).
            end_page: Last page (1-based, inclusive).
            add_page_markers: Insert page-boundary markers between pages.

        Returns:
            Combined text string.
        """
        self._ensure_open()

        start_page = max(1, start_page)
        end_page = min(end_page, len(self._doc))

        if start_page > end_page:
            logger.warning(
                f"Start page ({start_page}) > end page ({end_page})"
            )
            return ""

        text_parts: List[str] = []

        for page_num in range(start_page, end_page + 1):
            try:
                page = self._doc[page_num - 1]
                page_text = page.get_text()

                if add_page_markers:
                    # NOTE: Chinese markers are intentional – they serve as
                    # LLM-facing boundary tokens and changing the language
                    # may affect extraction quality.
                    text_parts.append(
                        f"========== 第{page_num}页 ==========\n"
                        f"{page_text}\n"
                        f"========== 第{page_num}页结束 =========="
                    )
                else:
                    text_parts.append(page_text)

            except Exception as e:
                logger.error(f"Failed to extract text from page {page_num}: {e}")
                continue

        combined = "\n\n".join(text_parts)
        logger.debug(
            f"Extracted pages {start_page}-{end_page}, "
            f"total length={len(combined)}"
        )
        return combined

    def get_page_count(self) -> int:
        """Return the total number of pages."""
        self._ensure_open()
        return len(self._doc)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def extract_page_text(pdf_path: str, page_num: int) -> str:
    """
    Extract text from a single page (convenience wrapper).

    Args:
        pdf_path: Path to the PDF file.
        page_num: 1-based page number.
    """
    with PDFReader(pdf_path) as reader:
        return reader.extract_page_text(page_num)


def extract_pages_text(
    pdf_path: str,
    start_page: int,
    end_page: int,
    add_page_markers: bool = True,
) -> str:
    """
    Extract text from a page range (convenience wrapper).

    Args:
        pdf_path: Path to the PDF file.
        start_page: First page (1-based, inclusive).
        end_page: Last page (1-based, inclusive).
        add_page_markers: Insert page-boundary markers.
    """
    with PDFReader(pdf_path) as reader:
        return reader.extract_pages_text(start_page, end_page, add_page_markers)


def get_pdf_page_count(pdf_path: str) -> int:
    """
    Return the total number of pages (convenience wrapper).

    Args:
        pdf_path: Path to the PDF file.
    """
    with PDFReader(pdf_path) as reader:
        return reader.get_page_count()


# Backward-compatible alias
PDFTextExtractor = PDFReader
