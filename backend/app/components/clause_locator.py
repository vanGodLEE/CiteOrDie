"""
LangGraph node – clause position locator.

Traverses every clause in the document tree and fills its ``positions``
field with bounding-box coordinates from the MinerU content list.

* **Visual clauses** (image / table) → matched by ``img_path`` or
  table lookup in the content list.
* **Text clauses** → matched via :class:`RequirementTextMatcher`
  fuzzy text matching.
"""

from typing import Any, Dict, List

from loguru import logger

from app.domain.schema import ClauseItem, DocumentAnalysisState, PageIndexNode
from app.tools.clause_text_matcher import RequirementTextMatcher, extract_node_content_list


def clause_locator_node(state: DocumentAnalysisState) -> Dict[str, Any]:
    """
    Locate bounding-box positions for every clause in the document tree.

    Reads:
        ``state["pageindex_document"]``, ``state["mineru_content_list"]``

    Side-effects:
        Mutates each :class:`ClauseItem` in-place (sets ``positions``).

    Returns:
        Empty dict (clauses are updated by reference).
    """
    logger.info("=" * 60)
    logger.info("Clause locator node started")
    logger.info("=" * 60)

    pageindex_doc = state.get("pageindex_document")
    mineru_content_list: list = state.get("mineru_content_list", [])

    if not pageindex_doc:
        logger.warning("No pageindex_document – skipping position locating")
        return {}

    if not mineru_content_list:
        logger.warning("No mineru_content_list – skipping position locating")
        return {}

    # Counters
    total = 0
    visual_count = 0
    text_count = 0
    located = 0
    failed = 0

    for root_node in pageindex_doc.structure:
        for node in root_node.get_all_nodes():
            if not node.clauses:
                continue

            logger.info(
                f"Processing node '{node.title}': {len(node.clauses)} clause(s)"
            )

            for clause in node.clauses:
                total += 1
                is_visual = bool(clause.image_caption or clause.table_caption)

                if is_visual:
                    visual_count += 1
                    positions = _locate_visual_clause(
                        clause, node, mineru_content_list,
                    )
                    logger.debug(
                        f"  [visual] {clause.matrix_id}: "
                        f"{len(positions)} bbox(es) matched"
                    )
                else:
                    text_count += 1
                    positions = _locate_text_clause(
                        clause, node, mineru_content_list,
                    )
                    logger.debug(
                        f"  [text] {clause.matrix_id}: "
                        f"{len(positions)} bbox(es) matched"
                    )

                if positions:
                    clause.positions = positions
                    located += 1
                else:
                    clause.positions = []
                    failed += 1
                    logger.warning(
                        f"  Position locating failed: {clause.matrix_id} | "
                        f"text: {clause.original_text[:50]}..."
                    )

    # Summary
    logger.info("Clause locating complete")
    logger.info(f"  Total clauses: {total}")
    logger.info(f"  Visual (image/table): {visual_count}")
    logger.info(f"  Text: {text_count}")
    logger.info(f"  Located: {located}")
    logger.info(f"  Failed: {failed}")

    if total > 0:
        rate = located / total * 100
        logger.info(f"  Success rate: {rate:.1f}%")
        if rate < 95:
            logger.warning(
                f"Location success rate is low ({rate:.1f}%) – "
                "review the text-matching algorithm"
            )

    return {}


# ---------------------------------------------------------------------------
# Visual clause locating
# ---------------------------------------------------------------------------

def _locate_visual_clause(
    clause: ClauseItem,
    node: PageIndexNode,
    mineru_content_list: List[Dict[str, Any]],
) -> List[List[int]]:
    """
    Locate a visual (image / table) clause's positions.

    Priority:
    1. Exact ``img_path`` match in the content list.
    2. First table bbox within the node's page range (fallback).
    3. Node-level positions (last resort).
    """
    # Strategy 1: exact img_path match
    if clause.img_path:
        positions = _find_content_by_img_path(clause.img_path, mineru_content_list)
        if positions:
            logger.debug(
                f"img_path match for {clause.matrix_id}: {clause.img_path}"
            )
            return positions
        logger.warning(
            f"Clause {clause.matrix_id}: img_path={clause.img_path} "
            "not found in content list – trying fallback"
        )

    # Strategy 2: table fallback (only when no img_path)
    if clause.table_caption and not clause.img_path:
        table_pos = _find_table_positions(node, mineru_content_list)
        if table_pos:
            logger.debug(
                f"Table fallback for {clause.matrix_id}: "
                f"{len(table_pos)} bbox(es)"
            )
            return table_pos

    # Strategy 3: node-level fallback
    if node.positions:
        logger.debug(
            f"Node fallback for {clause.matrix_id} -> "
            f"node '{node.title}' ({len(node.positions)} bboxes)"
        )
        return node.positions.copy()

    logger.warning(
        f"All strategies failed for {clause.matrix_id}: "
        f"node '{node.title}' has no positions either"
    )
    return []


def _find_content_by_img_path(
    img_path: str,
    mineru_content_list: List[Dict[str, Any]],
) -> List[List[int]]:
    """
    Find a content item by ``img_path`` and return its bbox as a position.

    Returns:
        ``[[page_idx, x1, y1, x2, y2]]`` or ``[]``.
    """
    for item in mineru_content_list:
        if item.get("img_path", "") == img_path:
            bbox = item.get("bbox")
            page_idx = item.get("page_idx")

            if bbox and page_idx is not None and len(bbox) == 4:
                logger.debug(
                    f"Exact img_path match: {img_path} -> "
                    f"type={item.get('type', '?')}, page={page_idx}"
                )
                return [[page_idx] + bbox]

            logger.warning(
                f"Found img_path={img_path} but bbox is invalid: "
                f"bbox={bbox}, page_idx={page_idx}"
            )
            return []

    logger.warning(f"img_path not found in content list: {img_path}")
    return []


def _find_table_positions(
    node: PageIndexNode,
    mineru_content_list: List[Dict[str, Any]],
) -> List[List[int]]:
    """
    Find the first table bbox within the node's page range.

    Returns:
        ``[[page_idx, x1, y1, x2, y2]]`` or ``[]``.
    """
    node_content = extract_node_content_list(
        node_positions=node.positions,
        full_content_list=mineru_content_list,
    )

    for item in node_content:
        if item.get("type") == "table":
            bbox = item.get("bbox")
            page_idx = item.get("page_idx")
            if bbox and page_idx is not None and len(bbox) == 4:
                logger.debug(
                    f"Table found: page={page_idx}, bbox={bbox}"
                )
                return [[page_idx] + bbox]

    logger.debug(f"No table content in node '{node.title}'")
    return []


# ---------------------------------------------------------------------------
# Text clause locating
# ---------------------------------------------------------------------------

def _locate_text_clause(
    clause: ClauseItem,
    node: PageIndexNode,
    mineru_content_list: List[Dict[str, Any]],
) -> List[List[int]]:
    """
    Locate a text clause via fuzzy matching against the content list.

    Narrows the search to the node's content slice, then delegates to
    :class:`RequirementTextMatcher`.
    """
    node_content = extract_node_content_list(
        node_positions=node.positions,
        full_content_list=mineru_content_list,
    )

    if not node_content:
        logger.warning(
            f"Node '{node.title}' content list is empty – "
            f"cannot locate clause {clause.matrix_id}"
        )
        return []

    return RequirementTextMatcher.find_requirement_positions(
        requirement_text=clause.original_text,
        node_content_list=node_content,
        node_positions=node.positions,
    )


# Backward-compatible alias
requirement_locator_node = clause_locator_node
