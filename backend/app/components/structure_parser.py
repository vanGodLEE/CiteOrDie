"""
LangGraph node – document structure parser.

Invokes the PageIndex client to analyse a PDF and produce a
hierarchical :class:`PageIndexDocument` tree.
"""

from typing import Any, Dict

from loguru import logger

from app.services.task_tracker import TaskTracker
from app.domain.schema import DocumentAnalysisState, PageIndexDocument, PageIndexNode
from app.services.pageindex_client import get_pageindex_client
from app.tools.progress_helper import log_step, update_progress


def structure_parser_node(state: DocumentAnalysisState) -> Dict[str, Any]:
    """
    Parse the PDF into a document-tree structure.

    Reads:
        ``state["pdf_path"]``

    Writes:
        ``state["pageindex_document"]`` – a :class:`PageIndexDocument`.

    Workflow:
    1. Call the PageIndex client to parse the PDF.
    2. Build a hierarchical :class:`PageIndexDocument` from the raw result.
    3. Report statistics (total nodes, leaf nodes).
    """
    logger.info("=" * 60)
    logger.info("Structure parser node started")
    logger.info("=" * 60)

    pdf_path = state["pdf_path"]
    task_id = state.get("task_id")

    update_progress(task_id, 5, "Preparing to parse document structure...")
    log_step(task_id, "Initialising document parser")

    try:
        # Obtain the PageIndex client singleton
        pi_client = get_pageindex_client()
        log_step(task_id, "PageIndex client loaded")

        # Parse the PDF
        logger.info(f"Invoking document parser on: {pdf_path}")
        update_progress(task_id, 8, "Identifying document TOC structure...")
        log_step(task_id, "Scanning pages and identifying heading hierarchy")

        result = pi_client.parse_pdf(pdf_path)

        log_step(task_id, "Parsing complete, building section tree")

        # Validate result
        if not isinstance(result, dict):
            raise ValueError(f"Parser returned unexpected type: {type(result)}")

        logger.debug(f"Parser result keys: {list(result.keys())}")

        structure = result.get("structure", [])
        logger.info(f"Found {len(structure)} root nodes")

        if not structure:
            logger.warning("Parser returned zero structure nodes; creating default root")
            structure = [{
                "node_id": "0",
                "title": "Full Document",
                "level": 0,
                "start_index": 1,
                "end_index": 999,
                "summary": "Complete document content",
                "nodes": [],
            }]

        # Convert to PageIndexDocument model
        try:
            pageindex_doc = PageIndexDocument(
                doc_name=result.get("doc_name", "unknown"),
                doc_description=result.get("doc_description"),
                structure=[PageIndexNode(**node) for node in structure],
            )
        except Exception as parse_error:
            logger.error(f"Failed to convert parser output: {parse_error}")
            logger.error(f"First node data: {structure[0] if structure else 'N/A'}")
            raise

        # Statistics
        total_nodes = len(pi_client.flatten_tree_to_nodes(result.get("structure", [])))
        leaf_nodes = pageindex_doc.get_all_leaf_nodes()

        logger.info("Structure parsing complete")
        logger.info(f"  Document: {pageindex_doc.doc_name}")
        logger.info(f"  Total nodes: {total_nodes}")
        logger.info(f"  Leaf nodes: {len(leaf_nodes)}")

        update_progress(task_id, 12, "Analysing document hierarchy")
        log_step(
            task_id,
            f"Found {total_nodes} nodes, {len(leaf_nodes)} sections for clause extraction",
        )
        update_progress(
            task_id, 15,
            "Document structure parsed",
            f"{len(leaf_nodes)} sections to process",
        )

        return {"pageindex_document": pageindex_doc}

    except Exception as e:
        error_msg = f"Structure parsing failed: {e}"
        logger.error(error_msg)

        if task_id:
            TaskTracker.log_progress(task_id, error_msg, 0)

        return {
            "error_message": error_msg,
            "pageindex_document": None,
        }


# Backward-compatible alias
pageindex_parser_node = structure_parser_node
