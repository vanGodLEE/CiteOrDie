"""
PageIndex document-structure extraction client.

Wraps the PageIndex library to parse a PDF into a hierarchical tree of
sections (nodes), handling Unicode decoding and rate-limit fallback at
the API layer.

Setup:
1. Place the ``pageindex`` package in the project root, *or*
2. Install it via ``pip install -e <path>``, *or*
3. Adjust the fallback path below.
"""

import codecs
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.domain.settings import settings

# ---------------------------------------------------------------------------
# PageIndex import (multiple resolution strategies)
# ---------------------------------------------------------------------------

try:
    from pageindex import page_index, config as pageindex_config  # noqa: F401

    logger.info("PageIndex module imported (installed package)")
except ImportError:
    # Fallback 1: look for a local ``pageindex/`` directory next to backend/
    _LOCAL_PI = Path(__file__).parent.parent.parent / "pageindex"

    # Fallback 2: hardcoded development path
    if not _LOCAL_PI.exists():
        _LOCAL_PI = Path("D:/dev/PageIndex")

    if _LOCAL_PI.exists() and str(_LOCAL_PI) not in sys.path:
        sys.path.insert(0, str(_LOCAL_PI))
        logger.info(f"Added PageIndex path: {_LOCAL_PI}")
        from pageindex import page_index, config as pageindex_config  # noqa: F401
    else:
        raise ImportError(
            "Cannot locate the PageIndex module. Ensure one of:\n"
            "  1. A 'pageindex/' directory exists at the project root, or\n"
            "  2. PageIndex is at D:/dev/PageIndex, or\n"
            "  3. PageIndex is installed via 'pip install -e'."
        )


class PageIndexClient:
    """
    Client for the PageIndex document-structure extraction library.

    Responsibilities:
    1. Invoke PageIndex to parse a PDF into a document tree.
    2. Decode escaped Unicode strings (e.g. CJK titles).
    3. Provide a stable interface consumed by the LangGraph workflow.

    Rate-limit (HTTP 429) fallback is handled inside the PageIndex
    API layer (``pageindex/utils.py``).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        toc_check_pages: int = 10,
        max_pages_per_node: int = 10,
        max_tokens_per_node: int = 8000,
        add_node_id: bool = True,
        add_node_summary: bool = False,
        add_doc_description: bool = False,
        add_node_text: bool = False,
    ) -> None:
        """
        Args:
            model: LLM model name; defaults to ``settings.structurizer_llm_name``.
            toc_check_pages: Number of leading pages to scan for a TOC.
            max_pages_per_node: Maximum pages per tree node.
            max_tokens_per_node: Maximum tokens per tree node.
            add_node_id: Assign a unique ID to each node.
            add_node_summary: Generate a summary for each node.
            add_doc_description: Generate a document-level description.
            add_node_text: Attach full text to each node.
        """
        self.model = model if model is not None else settings.structurizer_llm_name
        self.toc_check_pages = toc_check_pages
        self.max_pages_per_node = max_pages_per_node
        self.max_tokens_per_node = max_tokens_per_node
        self.add_node_id = add_node_id
        self.add_node_summary = add_node_summary
        self.add_doc_description = add_doc_description
        self.add_node_text = add_node_text

        logger.info("PageIndex client initialised")
        logger.info(f"  Model: {self.model}")
        logger.info("  Rate-limit fallback: handled by PageIndex API layer")

    # ------------------------------------------------------------------
    # Core parsing
    # ------------------------------------------------------------------

    def parse_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Parse a PDF into a hierarchical document tree.

        Rate-limit (429) fallback is handled inside the PageIndex API
        layer, so no retry logic is needed here.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            Dict with keys ``doc_name``, ``structure``
            (list of tree nodes), and optionally ``doc_description``.

        Raises:
            FileNotFoundError: If *pdf_path* does not exist.
            ValueError: If the file is not a PDF or the result is empty.
        """
        logger.info(f"Parsing PDF with PageIndex: {pdf_path}")

        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        if not pdf_path.lower().endswith(".pdf"):
            raise ValueError("Input file must be a PDF")

        try:
            logger.info(f"Model: {self.model}")
            logger.info(f"  TOC check pages: {self.toc_check_pages}")
            logger.info(f"  Max pages per node: {self.max_pages_per_node}")

            result = page_index(
                doc=pdf_path,
                model=self.model,
                toc_check_page_num=self.toc_check_pages,
                max_page_num_each_node=self.max_pages_per_node,
                max_token_num_each_node=self.max_tokens_per_node,
                if_add_node_id="yes" if self.add_node_id else "no",
                if_add_node_summary="yes" if self.add_node_summary else "no",
                if_add_doc_description="yes" if self.add_doc_description else "no",
                if_add_node_text="yes" if self.add_node_text else "no",
            )

            logger.info(f"PageIndex returned type: {type(result)}")

            if not result:
                raise ValueError("PageIndex returned an empty result")

            # Decode escaped Unicode sequences (e.g. \\uXXXX → real chars)
            result = self._decode_unicode_recursively(result)

            structure_count = len(result.get("structure", []))
            logger.info("PageIndex parsing complete")
            logger.info(f"  Document: {result.get('doc_name', 'unknown')}")
            logger.info(f"  Root nodes: {structure_count}")

            if structure_count == 0:
                logger.warning("PageIndex produced zero structure nodes")

            return result

        except Exception as e:
            logger.error(f"PageIndex parsing failed: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            logger.error(traceback.format_exc())
            raise

    # ------------------------------------------------------------------
    # Unicode helpers
    # ------------------------------------------------------------------

    def _decode_unicode_recursively(self, obj: Any) -> Any:
        """
        Recursively decode ``\\\\uXXXX`` escape sequences in strings.

        Args:
            obj: Any Python object (dict / list / str / …).

        Returns:
            The same structure with decoded strings.
        """
        if isinstance(obj, dict):
            return {k: self._decode_unicode_recursively(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._decode_unicode_recursively(item) for item in obj]
        if isinstance(obj, str):
            if "\\u" in obj:
                try:
                    return codecs.decode(obj, "unicode_escape")
                except Exception as e:
                    logger.warning(f"Unicode decode failed: {e}; returning original")
            return obj
        return obj

    # ------------------------------------------------------------------
    # Tree helpers
    # ------------------------------------------------------------------

    def flatten_tree_to_nodes(self, structure: List[Dict]) -> List[Dict]:
        """
        Flatten the tree into a list of node dicts (pre-order).

        Args:
            structure: Root node list from PageIndex.

        Returns:
            Flat list of node dicts with an added ``path`` key.
        """
        nodes: List[Dict] = []

        def _traverse(node_list: List[Dict], parent_path: str = "") -> None:
            for node in node_list:
                title = node.get("title", "Unknown")
                path = f"{parent_path}/{title}" if parent_path else title

                nodes.append({
                    "node_id": node.get("node_id"),
                    "title": title,
                    "start_index": node.get("start_index"),
                    "end_index": node.get("end_index"),
                    "summary": node.get("summary"),
                    "text": node.get("text"),
                    "path": path,
                    "has_children": bool(node.get("nodes")),
                })

                if node.get("nodes"):
                    _traverse(node["nodes"], path)

        _traverse(structure)
        logger.info(f"Flattened tree: {len(nodes)} nodes")
        return nodes

    def get_leaf_nodes(self, structure: List[Dict]) -> List[Dict]:
        """
        Collect all leaf nodes (nodes without children).

        Args:
            structure: Root node list from PageIndex.

        Returns:
            List of leaf-node dicts with an added ``path`` key.
        """
        leaves: List[Dict] = []

        def _traverse(node_list: List[Dict], parent_path: str = "") -> None:
            for node in node_list:
                title = node.get("title", "Unknown")
                path = f"{parent_path}/{title}" if parent_path else title

                if not node.get("nodes"):
                    leaves.append({
                        "node_id": node.get("node_id"),
                        "title": title,
                        "start_index": node.get("start_index"),
                        "end_index": node.get("end_index"),
                        "summary": node.get("summary"),
                        "text": node.get("text"),
                        "path": path,
                    })
                else:
                    _traverse(node["nodes"], path)

        _traverse(structure)
        logger.info(f"Extracted {len(leaves)} leaf nodes")
        return leaves


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_pageindex_client_instance: Optional[PageIndexClient] = None


def get_pageindex_client() -> PageIndexClient:
    """
    Return the module-level ``PageIndexClient`` singleton.

    Rate-limit (429) fallback is delegated to the PageIndex API layer.
    """
    global _pageindex_client_instance
    if _pageindex_client_instance is None:
        _pageindex_client_instance = PageIndexClient(
            model=settings.structurizer_llm_name,
            toc_check_pages=20,
            max_pages_per_node=10,
            max_tokens_per_node=20000,
            add_node_id=True,
            add_node_summary=False,   # summary derived from original_text instead
            add_doc_description=False,
            add_node_text=False,
        )
    return _pageindex_client_instance


# Backward-compatible aliases
PageIndexService = PageIndexClient
get_pageindex_service = get_pageindex_client
