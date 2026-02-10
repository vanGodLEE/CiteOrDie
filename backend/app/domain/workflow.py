"""
LangGraph workflow definition for document clause extraction.

Topology::

    START ─┬─→ structure_parser ──┐
           └─→ mineru_parser ─────┤
                                  ↓
                            parser_sync        (barrier: both parsers done)
                              ↓
                            text_filler [fan-out] (parallel: fill original_text per node)
                              ↓
                            text_fill_sync     (barrier: wait for all text fillers)
                              ↓
                            clause_extractor [fan-out] (parallel: LLM extraction per leaf)
                              ↓
                            clause_aggregator  (sort & normalise all clauses)
                              ↓
                            clause_locator     (match clause text -> PDF bounding boxes)
                              ↓
                             END

Key design decisions:
* ``structure_parser`` and ``mineru_parser`` run **in parallel** from START;
  ``parser_sync`` is a barrier that waits for both before proceeding.
* ``text_fill_sync`` is a mandatory barrier node.  Without it,
  ``_fan_out_clause_extractors`` would fire once per text-filler worker,
  causing N redundant clause-extraction passes.
* Both fan-out stages use LangGraph ``Send`` for parallel dispatch.
"""

import json
import uuid
from pathlib import Path
from typing import List, Dict, Any

from loguru import logger
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from app.domain.schema import DocumentAnalysisState, SectionState, PageIndexNode
from app.components.structure_parser import structure_parser_node
from app.components.mineru_parser import mineru_parser_node
from app.components.text_filler import text_filler_node
from app.components.clause_extractor import clause_extractor_node
from app.components.clause_aggregator import clause_aggregator_node
from app.components.clause_locator import clause_locator_node


# ===========================================================================
# Workflow builder
# ===========================================================================

def create_analysis_workflow():
    """
    Build and compile the document-analysis LangGraph workflow.

    Returns:
        A compiled ``StateGraph`` ready for ``.invoke()``.
    """
    workflow = StateGraph(DocumentAnalysisState)

    # -- Nodes ---------------------------------------------------------------
    workflow.add_node("structure_parser", structure_parser_node)
    workflow.add_node("mineru_parser", mineru_parser_node)
    workflow.add_node("parser_sync", _parser_sync_node)
    workflow.add_node("text_filler", text_filler_node)
    workflow.add_node("text_fill_sync", _text_fill_sync_node)
    workflow.add_node("clause_extractor", clause_extractor_node)
    workflow.add_node("clause_aggregator", clause_aggregator_node)
    workflow.add_node("clause_locator", clause_locator_node)

    # -- Edges ---------------------------------------------------------------
    # Phase 1: parallel parsing (both start simultaneously)
    workflow.add_edge(START, "structure_parser")
    workflow.add_edge(START, "mineru_parser")

    # Barrier: wait for both parsers before proceeding
    workflow.add_edge("structure_parser", "parser_sync")
    workflow.add_edge("mineru_parser", "parser_sync")

    # Fan-out: one text_filler per document node (parallel)
    workflow.add_conditional_edges("parser_sync", _fan_out_text_fillers)

    # Barrier: all text fillers must complete before clause extraction
    workflow.add_edge("text_filler", "text_fill_sync")

    # Fan-out: one clause_extractor per leaf node (parallel)
    workflow.add_conditional_edges("text_fill_sync", _fan_out_clause_extractors)

    # Remaining linear edges
    workflow.add_edge("clause_extractor", "clause_aggregator")
    workflow.add_edge("clause_aggregator", "clause_locator")
    workflow.add_edge("clause_locator", END)

    # -- Compile -------------------------------------------------------------
    graph = workflow.compile()
    logger.info(
        "Analysis workflow compiled "
        "(parallel parsers -> text fill -> clause extraction -> locating)"
    )

    return graph


# ===========================================================================
# Barrier: parallel parser sync
# ===========================================================================

def _parser_sync_node(state: DocumentAnalysisState) -> Dict[str, Any]:
    """
    Barrier node – waits for both ``structure_parser`` and ``mineru_parser``
    to finish before the workflow continues.

    Logs a summary of both parser outputs and sets a consolidated progress
    milestone (20%).
    """
    from app.tools.progress_helper import update_progress

    task_id = state.get("task_id")
    pageindex_doc = state.get("pageindex_document")
    mineru_content = state.get("mineru_content_list", [])
    error = state.get("error_message")

    logger.info("=" * 60)
    logger.info("Parser sync barrier reached (both parsers complete)")
    logger.info("=" * 60)

    if pageindex_doc:
        all_nodes = []
        for root in pageindex_doc.structure:
            all_nodes.extend(root.get_all_nodes())
        logger.info(f"  Structure parser: {len(all_nodes)} nodes")
    else:
        logger.warning("  Structure parser: FAILED or no output")

    logger.info(f"  MinerU parser: {len(mineru_content)} content items")

    if error:
        logger.error(f"  Errors reported: {error}")

    update_progress(task_id, 20, "Both parsers complete, preparing text fill phase")
    return {}


# ===========================================================================
# Fan-out routers
# ===========================================================================

def _fan_out_text_fillers(state: DocumentAnalysisState):
    """
    Fan-out router: dispatch one ``Send("text_filler", ...)`` per document node.

    Processes all nodes (both parent and leaf) so that every node gets
    its ``original_text`` filled from the MinerU content list.

    If the structure parser failed (error or missing document), the
    workflow terminates early by returning ``END``.
    """
    pageindex_doc = state.get("pageindex_document")
    pdf_path = state.get("pdf_path")
    task_id = state.get("task_id")
    error_message = state.get("error_message")

    if error_message or not pageindex_doc:
        logger.error(
            f"Structure parsing failed, terminating workflow: "
            f"{error_message or 'pageindex_document is None'}"
        )
        return END

    # Collect every node in the document tree
    all_nodes = []
    for root in pageindex_doc.structure:
        all_nodes.extend(root.get_all_nodes())

    if not all_nodes:
        logger.warning("No document nodes found; cannot dispatch text fillers")
        return []

    logger.info(f"Dispatching {len(all_nodes)} parallel text-filler tasks")

    mineru_content_list = state.get("mineru_content_list", [])
    mineru_output_dir = state.get("mineru_output_dir")

    sends = []
    for node in all_nodes:
        filler_state = {
            "node": node,
            "pdf_path": pdf_path,
            "task_id": task_id,
            "pageindex_document": pageindex_doc,
            "mineru_content_list": mineru_content_list,
            "mineru_output_dir": mineru_output_dir,
        }
        sends.append(Send("text_filler", filler_state))

    logger.info(f"Fan-out complete: {len(sends)} text-filler task(s) queued")
    return sends


def _fan_out_clause_extractors(state: DocumentAnalysisState) -> List[Send]:
    """
    Fan-out router: dispatch one ``Send("clause_extractor", ...)`` per leaf node.

    Runs after the ``text_fill_sync`` barrier, ensuring it fires exactly once.
    """
    pageindex_doc = state.get("pageindex_document")
    task_id = state.get("task_id")
    mineru_output_dir = state.get("mineru_output_dir")

    if not pageindex_doc:
        logger.warning("No document available; cannot dispatch clause extractors")
        return []

    leaf_nodes = pageindex_doc.get_all_leaf_nodes()

    if not leaf_nodes:
        logger.warning("No leaf nodes found; cannot dispatch clause extractors")
        return []

    logger.info(
        f"Dispatching {len(leaf_nodes)} parallel clause-extraction tasks "
        f"(text + vision)"
    )
    if mineru_output_dir:
        logger.info(f"  MinerU output dir: {mineru_output_dir}")
    else:
        logger.warning("  MinerU output dir not found; visual extraction will be skipped")

    sends = []
    for node in leaf_nodes:
        node.path = f"{node.node_id or 'UNKNOWN'}: {node.title}"

        section_state = SectionState(
            pageindex_node=node,
            task_id=task_id,
            mineru_output_dir=mineru_output_dir,
            section_node=None,
            content_blocks=None,
            section_id=node.node_id,
            section_title=node.title,
            section_plan=None,
            requirements=[],
        )
        sends.append(Send("clause_extractor", section_state))

    logger.info(f"Fan-out complete: {len(sends)} clause-extractor task(s) queued")
    return sends


# ===========================================================================
# Barrier / sync node
# ===========================================================================

def _text_fill_sync_node(state: DocumentAnalysisState) -> Dict[str, Any]:
    """
    Barrier node – waits for all parallel text-filler workers to finish.

    This node is essential: without it, ``_fan_out_clause_extractors``
    would be triggered once per text-filler worker, causing N redundant
    clause-extraction passes.

    Side-effects:
        * Logs fill-rate statistics.
        * Saves an intermediate JSON snapshot of the document tree.

    Returns:
        Empty dict (state is not modified; the document tree was already
        mutated in-place by the text-filler workers).
    """
    pageindex_doc = state.get("pageindex_document")
    pdf_path = state.get("pdf_path")

    if pageindex_doc:
        all_nodes = []
        for root in pageindex_doc.structure:
            all_nodes.extend(root.get_all_nodes())

        filled_count = sum(1 for node in all_nodes if node.original_text)
        total_count = len(all_nodes)

        logger.info("Text-fill phase complete")
        logger.info(f"  Total nodes: {total_count}")
        logger.info(f"  Filled: {filled_count}")
        logger.info(f"  Fill rate: {filled_count / total_count * 100:.1f}%")

        if pdf_path:
            _save_intermediate_json(pageindex_doc, pdf_path)

    return {}


# ===========================================================================
# Internal helpers
# ===========================================================================

def _save_intermediate_json(pageindex_doc, pdf_path: str) -> None:
    """
    Save the document tree (with ``original_text`` filled) as a JSON snapshot.

    The snapshot is written to ``middle_json/<pdf_stem>_<uuid>.json`` and is
    useful for debugging and offline inspection.

    Args:
        pageindex_doc: The :class:`PageIndexDocument` instance.
        pdf_path: Path to the source PDF (used for naming).
    """
    try:
        output_dir = Path("middle_json")
        output_dir.mkdir(exist_ok=True)

        pdf_stem = Path(pdf_path).stem
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{pdf_stem}_{unique_id}.json"
        filepath = output_dir / filename

        json_data = pageindex_doc.dict()
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(json_data, fh, ensure_ascii=False, indent=2)

        logger.info(f"Intermediate snapshot saved: {filepath}")

    except Exception as e:
        logger.error(f"Failed to save intermediate snapshot: {e}")


# ===========================================================================
# Backward-compatible aliases
# ===========================================================================

create_tender_analysis_graph = create_analysis_workflow
