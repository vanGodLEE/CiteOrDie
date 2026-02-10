"""
LangGraph node – MinerU content parser.

Runs in parallel with the structure parser to extract full document
content (text, images, tables) via the MinerU CLI tool.
"""

from typing import Dict, Any
from loguru import logger
from app.domain.schema import DocumentAnalysisState
from app.services.mineru_client import get_mineru_client
from app.services.task_tracker import TaskTracker
from app.tools.progress_helper import update_progress, log_step


def mineru_parser_node(state: DocumentAnalysisState) -> Dict[str, Any]:
    """
    Parse the PDF with MinerU to extract content blocks.

    Reads:
        ``state["pdf_path"]``, ``state["task_id"]``

    Writes:
        ``state["mineru_result"]``, ``state["mineru_content_list"]``,
        ``state["mineru_output_dir"]``
    """
    pdf_path = state.get("pdf_path")
    task_id = state.get("task_id")
    
    if not pdf_path:
        logger.error("pdf_path is missing; cannot invoke MinerU")
        return {
            "error_message": "Missing PDF file path for MinerU",
            "mineru_result": None,
            "mineru_content_list": [],
            "mineru_output_dir": None
        }
    
    update_progress(task_id, 5, "Starting MinerU deep parsing...")
    log_step(task_id, "Initialising MinerU PDF parsing engine")
    
    try:
        logger.info(f"Invoking MinerU on: {pdf_path}")
        log_step(task_id, "Scanning PDF pages for text, images, and tables")
        
        mineru_service = get_mineru_client()
        
        update_progress(task_id, 10, "Extracting document content (text + visuals)...")
        log_step(task_id, "Extracting page text and layout information")
        
        result = mineru_service.parse_pdf(
            pdf_path=pdf_path,
            task_id=task_id or "default"
        )
        
        log_step(task_id, "MinerU parsing complete, processing results")
        
        if not result:
            error_msg = "MinerU parsing failed: no result returned"
            logger.error(error_msg)
            return {
                "error_message": error_msg,
                "mineru_result": None,
                "mineru_content_list": [],
                "mineru_output_dir": None
            }
        
        # Extract key fields
        content_list = result.get("content_list", [])
        output_dir = result.get("output_dir")
        type_counts = result.get("type_counts", {})
        
        logger.info("MinerU parsing complete")
        logger.info(f"  Total items: {len(content_list)}")
        logger.info(f"  Text: {type_counts.get('text', 0)}")
        logger.info(f"  List: {type_counts.get('list', 0)}")
        logger.info(f"  Image: {type_counts.get('image', 0)}")
        logger.info(f"  Table: {type_counts.get('table', 0)}")
        logger.info(f"  Output dir: {output_dir}")
        
        if task_id:
            TaskTracker.log_progress(
                task_id,
                f"MinerU parsing done: {len(content_list)} content items extracted",
                15,
            )
        
        return {
            "mineru_result": result,
            "mineru_content_list": content_list,
            "mineru_output_dir": output_dir
        }
        
    except Exception as e:
        error_msg = f"MinerU parsing error: {e}"
        logger.error(error_msg)
        logger.exception(e)
        
        return {
            "error_message": error_msg,
            "mineru_result": None,
            "mineru_content_list": [],
            "mineru_output_dir": None
        }