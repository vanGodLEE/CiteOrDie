"""
Analysis API endpoints.

Provides endpoints for uploading PDF documents, running the clause-extraction
pipeline, streaming progress via SSE, retrieving results, and downloading
exports.

Idempotency: duplicate uploads (same SHA-256 hash) are detected and the
existing completed task is reused automatically.
"""

import json
import asyncio
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse, Response
from loguru import logger

from app.domain.schema import DocumentAnalysisState, PageIndexDocument
from app.domain.workflow import create_analysis_workflow
from app.datasources.crud import ClauseRepository, SectionRepository, TaskRepository
from app.datasources.database import get_db_session
from app.services.clause_matrix_export import ClauseMatrixExporter
from app.services.task_tracker import TaskTracker

router = APIRouter()


# ===========================================================================
# Background pipeline
# ===========================================================================

async def _run_analysis_pipeline(task_id: str, pdf_path: str) -> None:
    """
    Background task: run the full clause-extraction pipeline.

    Orchestrates:
    1. LangGraph workflow execution (structure + content + clauses + locating).
    2. Persistence of sections and clauses to the database.
    3. Quality-report generation.
    4. Coordinate conversion for frontend rendering.
    5. Task completion update.
    """
    try:
        TaskTracker.update_task(
            task_id, status="running", progress=0,
            message="Starting analysis...",
        )

        # Build initial state and run the workflow in a background thread
        initial_state = DocumentAnalysisState(
            pdf_path=pdf_path,
            use_mock=False,
            task_id=task_id,
            pageindex_document=None,
            content_list=[],
            markdown="",
            toc=[],
            toc_tree=None,
            target_sections=[],
            clauses=[],
            final_matrix=[],
            processing_start_time=None,
            processing_end_time=None,
            error_message=None,
        )

        graph = create_analysis_workflow()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, graph.invoke, initial_state)

        if result.get("error_message"):
            raise Exception(result["error_message"])

        final_matrix = result.get("final_matrix", [])
        pageindex_doc = result.get("pageindex_document")

        # Cache page dimensions once (avoids reopening the PDF per clause)
        page_dims = _cache_page_dimensions(pdf_path)

        # Persist sections + clauses to the database
        _persist_analysis_results(
            task_id, pdf_path, final_matrix, pageindex_doc, page_dims,
        )

        # Serialise the document tree
        tree_data = pageindex_doc.model_dump() if pageindex_doc else None

        # Generate quality report (non-blocking; failure is tolerated)
        quality_report = _build_quality_report(
            pdf_path, tree_data, final_matrix,
        )

        # Convert all tree-node positions for frontend rendering
        if tree_data and tree_data.get("structure"):
            for root_node in tree_data["structure"]:
                _convert_tree_positions(root_node, pdf_path, page_dims)
            logger.info("Document-tree positions converted to page coordinates")

        # Mark the task as completed
        TaskTracker.update_task(
            task_id,
            status="completed",
            progress=100,
            message=f"Analysis complete: {len(final_matrix)} clause(s) extracted",
            result={
                "clauses_count": len(final_matrix),
                "document_tree": tree_data,
                "quality_report": quality_report,
            },
            document_tree=tree_data,
            quality_report=quality_report,
        )

    except Exception as e:
        error_msg = f"Analysis failed: {e}"
        logger.error(error_msg)
        logger.exception(e)
        TaskTracker.update_task(
            task_id, status="failed", progress=0, message=error_msg,
        )


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------

def _cache_page_dimensions(pdf_path: str):
    """Pre-fetch page dimensions so coordinate conversion can skip re-opening the PDF."""
    from app.tools.mineru_coordinate_converter import get_all_page_dimensions

    logger.info(f"Caching page dimensions: {pdf_path}")
    try:
        dims = get_all_page_dimensions(pdf_path)
        logger.info(f"Cached dimensions for {len(dims)} page(s)")
        return dims
    except Exception as e:
        logger.warning(f"Failed to cache page dimensions (will fetch on-demand): {e}")
        return None


def _persist_analysis_results(
    task_id: str,
    pdf_path: str,
    final_matrix: list,
    pageindex_doc,
    page_dims,
) -> None:
    """Save sections and clauses to the database with coordinate conversion."""
    from app.tools.mineru_coordinate_converter import convert_positions_for_frontend

    db = get_db_session()
    try:
        # Sections (from leaf nodes)
        if pageindex_doc:
            leaf_nodes = pageindex_doc.get_all_leaf_nodes()
            sections_data = [
                {
                    "section_id": node.node_id or "UNKNOWN",
                    "title": node.title,
                    "start_page": node.start_index,
                    "end_page": node.end_index,
                }
                for node in leaf_nodes
            ]
            SectionRepository.batch_create_sections(db, task_id, sections_data)

        # Clauses (with coordinate conversion)
        clauses_data: List[Dict] = []
        for clause in final_matrix:
            positions = clause.positions if hasattr(clause, "positions") else []
            if positions:
                try:
                    positions = convert_positions_for_frontend(
                        positions, pdf_path=pdf_path, page_dimensions=page_dims,
                    )
                except Exception as e:
                    logger.warning(
                        f"Coordinate conversion failed for {clause.matrix_id}: {e}"
                    )

            clauses_data.append({
                "matrix_id": clause.matrix_id,
                "type": clause.type,
                "actor": clause.actor,
                "action": clause.action,
                "object": clause.object,
                "condition": clause.condition,
                "deadline": clause.deadline,
                "metric": clause.metric,
                "original_text": clause.original_text,
                "section_id": clause.section_id,
                "section_title": clause.section_title,
                "page_number": clause.page_number,
                "image_caption": getattr(clause, "image_caption", None),
                "table_caption": getattr(clause, "table_caption", None),
                "positions": positions,
            })

        ClauseRepository.batch_create_clauses(db, task_id, clauses_data)
    finally:
        db.close()


def _build_quality_report(
    pdf_path: str,
    tree_data: Optional[dict],
    final_matrix: list,
) -> Optional[dict]:
    """Generate a quality report.  Returns ``None`` on failure (non-fatal)."""
    try:
        from app.services.quality_report import QualityReportService

        if not tree_data or not final_matrix:
            logger.warning("Insufficient data for quality report; skipping")
            return None

        logger.info("Generating quality report...")

        matrix_dicts = []
        for clause in final_matrix:
            if hasattr(clause, "model_dump"):
                matrix_dicts.append(clause.model_dump())
            elif hasattr(clause, "dict"):
                matrix_dicts.append(clause.dict())
            else:
                matrix_dicts.append(dict(clause))

        report = QualityReportService.generate_report(
            pdf_path=pdf_path,
            document_tree=tree_data,
            final_matrix=matrix_dicts,
        )
        logger.info("Quality report generated")
        return report.model_dump()

    except Exception as e:
        logger.error(f"Quality report generation failed (non-fatal): {e}")
        logger.exception(e)
        return None


def _convert_tree_positions(
    node_data: dict,
    pdf_path: str,
    page_dims,
) -> None:
    """Recursively convert bounding-box positions in the document tree."""
    from app.tools.mineru_coordinate_converter import convert_positions_for_frontend

    if node_data.get("positions"):
        try:
            node_data["positions"] = convert_positions_for_frontend(
                node_data["positions"],
                pdf_path=pdf_path,
                page_dimensions=page_dims,
            )
        except Exception as e:
            logger.warning(
                f"Position conversion failed for node '{node_data.get('title')}': {e}"
            )

    for child in node_data.get("nodes", []):
        _convert_tree_positions(child, pdf_path, page_dims)


def _calculate_file_hash(content: bytes) -> str:
    """Return the SHA-256 hex digest of *content*."""
    return hashlib.sha256(content).hexdigest()


# ===========================================================================
# POST /analyze – upload and start analysis
# ===========================================================================

@router.post("/analyze")
async def analyze_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Upload a PDF and start clause extraction (idempotent).

    Idempotency strategy:
    1. Compute SHA-256 of the uploaded file.
    2. If a completed task with the same hash exists, return it (``reused=true``).
    3. If an identical file is currently being analysed, return its task ID.
    4. Otherwise, create a new task and launch the background pipeline.
    """
    if not file.filename.lower().endswith(".pdf"):
        return {"status": "error", "message": "Only PDF files are supported"}

    content = await file.read()
    file_size = len(content)
    file_hash = _calculate_file_hash(content)
    logger.info(f"File hash: {file_hash[:16]}...")

    # --- Idempotency check ---------------------------------------------------
    db = get_db_session()
    try:
        existing = TaskRepository.find_by_file_hash(db, file_hash)

        if existing and existing.status == "completed":
            logger.info(
                f"Reusing completed task: {existing.task_id} "
                f"(file: {existing.file_name})"
            )
            if not TaskTracker.get_task(existing.task_id):
                TaskTracker.load_completed_task(existing.task_id)

            return {
                "status": "success",
                "task_id": existing.task_id,
                "reused": True,
                "message": (
                    f"Duplicate file detected; reusing result "
                    f"(completed {existing.completed_at:%Y-%m-%d %H:%M:%S})"
                ),
            }

        if existing and existing.status == "running":
            logger.info(f"Task already running: {existing.task_id}")
            return {
                "status": "success",
                "task_id": existing.task_id,
                "reused": True,
                "message": "This file is already being analysed; please wait",
            }

        # No reusable task found (or previous attempt failed)
        if existing:
            logger.info(
                f"Previous task status is '{existing.status}'; creating new task"
            )
        else:
            logger.info("First upload of this file; creating new task")
    finally:
        db.close()

    # --- Save uploaded file ---------------------------------------------------
    upload_dir = Path("temp/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename

    with open(file_path, "wb") as fh:
        fh.write(content)
    logger.info(f"File saved: {file_path}")

    # --- Create task ----------------------------------------------------------
    task_id = TaskTracker.create_task(
        pdf_path=str(file_path),
        file_name=file.filename,
        file_size=file_size,
        file_hash=file_hash,
    )

    # --- Upload to object storage (non-blocking) -----------------------------
    try:
        from app.services.object_storage import get_object_storage_service

        storage = get_object_storage_service()
        minio_url = storage.upload_pdf(str(file_path), task_id)

        db = get_db_session()
        try:
            TaskRepository.update_task(db, task_id, {"minio_url": minio_url})
        finally:
            db.close()
        logger.info(f"PDF uploaded to object storage: {minio_url}")
    except Exception as e:
        logger.warning(f"Object storage upload failed (non-fatal): {e}")

    # --- Launch background pipeline -------------------------------------------
    background_tasks.add_task(
        _run_analysis_pipeline, task_id=task_id, pdf_path=str(file_path),
    )

    return {
        "status": "success",
        "task_id": task_id,
        "reused": False,
        "message": "Task created; subscribe to progress via task_id",
    }


# ===========================================================================
# GET /progress/{task_id} – SSE progress stream
# ===========================================================================

@router.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """Stream real-time progress for a task via Server-Sent Events."""

    async def _event_generator():
        last_progress = -1
        polls = 0
        max_polls = 600  # ~10 minutes at 1 s intervals

        while polls < max_polls:
            task = TaskTracker.get_task(task_id)

            if not task:
                yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
                break

            current_progress = task["progress"]
            if current_progress != last_progress:
                payload = {
                    **task,
                    "created_at": (
                        task["created_at"].isoformat()
                        if isinstance(task.get("created_at"), datetime)
                        else task.get("created_at")
                    ),
                    "updated_at": (
                        task["updated_at"].isoformat()
                        if isinstance(task.get("updated_at"), datetime)
                        else task.get("updated_at")
                    ),
                    "start_time": (
                        task["start_time"].isoformat()
                        if task.get("start_time")
                        and isinstance(task["start_time"], datetime)
                        else None
                    ),
                    "elapsed_seconds": task.get("elapsed_seconds", 0),
                    "logs": task.get("logs", []),
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                last_progress = current_progress

            if task["status"] in ("completed", "failed"):
                break

            await asyncio.sleep(1)
            polls += 1

        yield f"data: {json.dumps({'status': 'done'})}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ===========================================================================
# GET /task/{task_id} – full task result
# ===========================================================================

@router.get("/task/{task_id}")
async def get_task_result(task_id: str):
    """
    Return the full task result including clause matrix, document tree,
    and quality report.

    For completed tasks the data is loaded from the database (survives
    process restarts).  Bounding-box positions are already converted to
    page coordinates (top-left origin, points).
    """
    task = TaskTracker.get_task(task_id)
    if not task:
        return {"status": "error", "message": "Task not found"}

    if task["status"] == "completed":
        db = get_db_session()
        try:
            clauses_data = ClauseRepository.get_clauses_with_positions(db, task_id)
            task_record = TaskRepository.get_task(db, task_id)

            # Clause matrix
            task["matrix"] = clauses_data
            task["clauses_count"] = len(clauses_data)

            # Document tree (prefer in-memory cache, fall back to DB)
            document_tree = _load_json_field(
                task, "document_tree",
                task_record, "document_tree_json",
            )
            task["document_tree"] = document_tree

            # Quality report
            quality_report = _load_json_field(
                task, "quality_report",
                task_record, "quality_report_json",
            )
            task["quality_report"] = quality_report

            logger.info(f"Task {task_id}: returning {len(clauses_data)} clause(s)")
            if quality_report:
                confidence = quality_report.get("avg_parse_confidence", 0)
                logger.info(f"  Quality report: parse confidence={confidence:.2%}")
        finally:
            db.close()

    return task


def _load_json_field(
    task: dict,
    memory_key: str,
    db_record,
    db_json_attr: str,
):
    """Load a JSON field from in-memory result or fall back to the DB record."""
    # Try in-memory first
    if task.get("result") and isinstance(task["result"], dict):
        value = task["result"].get(memory_key)
        if value:
            return value

    # Fall back to database
    if db_record:
        raw_json = getattr(db_record, db_json_attr, None)
        if raw_json:
            try:
                return json.loads(raw_json)
            except Exception as e:
                logger.error(f"Failed to parse {db_json_attr}: {e}")

    return None


# ===========================================================================
# GET /download/excel/{task_id} – Excel export
# ===========================================================================

@router.get("/download/excel/{task_id}")
async def download_excel(task_id: str):
    """Download the clause matrix as an Excel workbook."""
    task = TaskTracker.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    document_tree = None
    if task.get("result") and isinstance(task["result"], dict):
        document_tree = task["result"].get("document_tree")
    if not document_tree:
        raise HTTPException(status_code=404, detail="Document tree data not found")

    try:
        doc = PageIndexDocument(**document_tree)
        excel_bytes = ClauseMatrixExporter.export_to_excel(doc)
        file_name = ClauseMatrixExporter.get_filename(doc.doc_name)
        encoded_filename = quote(file_name.encode("utf-8"))

        return Response(
            content=excel_bytes.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="clause_matrix.xlsx"; '
                    f"filename*=UTF-8''{encoded_filename}"
                ),
            },
        )
    except Exception as e:
        logger.error(f"Excel generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Excel generation failed: {e}")


# ===========================================================================
# GET /quality-report/{task_id}
# ===========================================================================

@router.get("/quality-report/{task_id}")
async def get_quality_report(task_id: str):
    """Return the quality report for a completed task."""
    task = TaskTracker.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task not yet completed")

    db = get_db_session()
    try:
        task_record = TaskRepository.get_task(db, task_id)
        if not task_record:
            raise HTTPException(status_code=404, detail="Task record not found")

        quality_report = _load_json_field(
            task, "quality_report",
            task_record, "quality_report_json",
        )

        if not quality_report:
            raise HTTPException(
                status_code=404,
                detail="Quality report not found (try re-analysing)",
            )

        return {
            "status": "success",
            "task_id": task_id,
            "file_name": task_record.file_name,
            "quality_report": quality_report,
        }
    finally:
        db.close()


# ===========================================================================
# DELETE /task/{task_id}
# ===========================================================================

@router.delete("/task/{task_id}")
async def delete_task(task_id: str):
    """
    Delete a task and all associated resources.

    Removes: database records (task, logs, sections, clauses), object-storage
    objects, local PDF, MinerU output, and intermediate files.
    """
    from app.services.task_cleanup import TaskCleanupService

    db = get_db_session()
    try:
        task_record = TaskRepository.get_task(db, task_id)
        if not task_record:
            raise HTTPException(status_code=404, detail="Task not found")

        logger.info(f"Deleting task: {task_id} ({task_record.file_name})")

        # Clean up associated files
        cleanup = TaskCleanupService.cleanup_task(
            task_id=task_id,
            pdf_path=task_record.pdf_path,
            file_name=task_record.file_name,
        )

        # Delete database records (cascade)
        cleanup["database"] = TaskRepository.delete_task(db, task_id)

        # Evict from in-memory cache
        TaskTracker.delete_task(task_id)

        success = [k for k, v in cleanup.items() if v and k != "task_id"]
        total = len(cleanup) - 1
        logger.info(f"Task deleted: {task_id} ({len(success)}/{total} items)")

        return {
            "status": "success",
            "task_id": task_id,
            "message": f"Task deleted ({len(success)}/{total} items succeeded)",
            "details": cleanup,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete task: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=f"Task deletion failed: {e}")
    finally:
        db.close()


# ===========================================================================
# GET /pdf/{task_id} – presigned PDF URL
# ===========================================================================

@router.get("/pdf/{task_id}")
async def get_pdf_url(task_id: str):
    """Generate a presigned URL for the task's PDF (valid 24 h)."""
    task = TaskTracker.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db = get_db_session()
    try:
        task_record = TaskRepository.get_task(db, task_id)
        if not task_record:
            raise HTTPException(status_code=404, detail="Task record not found")

        try:
            from app.services.object_storage import get_object_storage_service

            storage = get_object_storage_service()
            direct_url, proxy_url = storage.get_pdf_url(task_id)

            if not direct_url:
                raise HTTPException(status_code=404, detail="PDF not found in storage")

            logger.debug(f"Presigned URL generated (direct): {direct_url[:80]}...")

            return {
                "status": "success",
                "task_id": task_id,
                "file_name": task_record.file_name,
                "minio_url": direct_url,
                "proxy_url": proxy_url,
                "message": "PDF URL generated (valid 24 h)",
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise HTTPException(
                status_code=500, detail=f"Presigned URL generation failed: {e}",
            )
    finally:
        db.close()
