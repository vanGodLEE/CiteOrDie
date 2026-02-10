"""
Query endpoints.

Read-only API for listing/searching tasks, logs, sections, and clauses.
"""

from typing import List, Optional, Union
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from datetime import datetime
from loguru import logger

from app.datasources.database import get_db_session
from app.datasources.crud import TaskRepository, TaskLogRepository, SectionRepository, ClauseRepository

router = APIRouter(prefix="/api")


# ============================================================================
# Response models
# ============================================================================

class TaskSummary(BaseModel):
    """Compact task overview returned by the list endpoint."""
    task_id: str
    file_name: str
    status: str
    progress: float
    total_sections: int
    total_clauses: int
    total_requirements: int  # kept for backward compatibility
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    elapsed_seconds: float


class TaskDetail(BaseModel):
    """Full task information including error/progress messages."""
    task_id: str
    file_name: str
    file_size: int
    status: str
    progress: float
    current_message: Optional[str]
    error_message: Optional[str]
    total_sections: int
    total_clauses: int
    total_requirements: int  # kept for backward compatibility
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    elapsed_seconds: float


class LogEntry(BaseModel):
    """Single log record produced during task execution."""
    id: int
    log_level: str
    progress: Optional[float]
    message: str
    created_at: datetime


class SectionSummary(BaseModel):
    """Summary of a document section selected by the analysis."""
    section_id: str
    title: str
    reason: Optional[str]
    priority: int
    start_page: int


class ClauseSummary(BaseModel):
    """Compact clause representation (no positional data)."""
    matrix_id: str
    type: str
    actor: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    original_text: str
    section_title: str
    page_number: int


class ClauseDetail(BaseModel):
    """Full clause with positional data for PDF highlighting."""
    matrix_id: str
    node_id: str  # section_id that owns this clause
    section_title: str
    type: str
    actor: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    condition: Optional[str] = None
    deadline: Optional[str] = None
    metric: Optional[str] = None
    original_text: str
    page_number: int
    image_caption: Optional[str] = None
    table_caption: Optional[str] = None
    # PDF coordinates: [[page_idx(int), x0, y0, x1, y1], ...]
    positions: List[List[Union[int, float]]] = []


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/tasks", response_model=List[TaskSummary])
def list_tasks(
    status: Optional[str] = Query(None, description="Filter by task status"),
    limit: int = Query(50, le=100, description="Maximum number of results"),
    offset: int = Query(0, description="Pagination offset"),
):
    """Return a paginated list of tasks, optionally filtered by status."""
    db = get_db_session()
    try:
        tasks = TaskRepository.list_tasks(db, status=status, limit=limit, offset=offset)

        return [
            TaskSummary(
                task_id=t.task_id,
                file_name=t.file_name,
                status=t.status,
                progress=t.progress,
                total_sections=t.total_sections,
                total_clauses=t.total_clauses or 0,
                total_requirements=t.total_requirements or 0,
                created_at=t.created_at,
                started_at=t.started_at,
                completed_at=t.completed_at,
                elapsed_seconds=t.elapsed_seconds or 0.0,
            )
            for t in tasks
        ]
    finally:
        db.close()


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task_detail(task_id: str):
    """Return detailed information for a single task."""
    db = get_db_session()
    try:
        task = TaskRepository.get_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        return TaskDetail(
            task_id=task.task_id,
            file_name=task.file_name,
            file_size=task.file_size,
            status=task.status,
            progress=task.progress,
            current_message=task.current_message,
            error_message=task.error_message,
            total_sections=task.total_sections,
            total_clauses=task.total_clauses or 0,
            total_requirements=task.total_requirements or 0,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            elapsed_seconds=task.elapsed_seconds or 0.0,
        )
    finally:
        db.close()


@router.get("/tasks/{task_id}/logs", response_model=List[LogEntry])
def get_task_logs(task_id: str):
    """Return execution logs for a task (useful for post-mortem review)."""
    db = get_db_session()
    try:
        logs = TaskLogRepository.get_logs(db, task_id)

        return [
            LogEntry(
                id=log.id,
                log_level=log.log_level,
                progress=log.progress,
                message=log.message,
                created_at=log.created_at,
            )
            for log in logs
        ]
    finally:
        db.close()


@router.get("/tasks/{task_id}/sections", response_model=List[SectionSummary])
def get_task_sections(task_id: str):
    """Return sections selected during the analysis for a task."""
    db = get_db_session()
    try:
        sections = SectionRepository.get_sections(db, task_id)

        return [
            SectionSummary(
                section_id=sec.section_id,
                title=sec.title,
                reason=sec.reason,
                priority=sec.priority,
                start_page=sec.start_page,
            )
            for sec in sections
        ]
    finally:
        db.close()


@router.get("/tasks/{task_id}/clauses", response_model=List[ClauseSummary])
def get_task_clauses(task_id: str):
    """Return extracted clauses for a task (compact, no positions)."""
    db = get_db_session()
    try:
        clauses = ClauseRepository.get_clauses(db, task_id)

        return [
            ClauseSummary(
                matrix_id=clause.matrix_id,
                type=clause.clause_type,
                actor=clause.actor,
                action=clause.action,
                object=clause.object,
                original_text=clause.original_text,
                section_title=clause.section_title,
                page_number=clause.page_number,
            )
            for clause in clauses
        ]
    finally:
        db.close()


@router.get("/tasks/{task_id}/clauses/all", response_model=List[ClauseDetail])
def get_all_clauses_flat(task_id: str):
    """
    Return all clauses for a task as a flat list ordered by page number.

    Each clause includes full metadata and PDF bounding-box coordinates.
    The ``positions`` field contains page-space coordinates (top-left origin,
    in PDF points).  Frontend usage:

    1. Compute scale:  ``scale = containerWidth / viewport.width``
    2. Apply scale:    ``vx = x * scale``, ``vy = y * scale``
    3. Draw highlight: ``ctx.strokeRect(vx0, vy0, vx1-vx0, vy1-vy0)``
    """
    db = get_db_session()
    try:
        task = TaskRepository.get_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        clauses_data = ClauseRepository.get_clauses_with_positions(db, task_id)

        result = []
        for clause in clauses_data:
            result.append(ClauseDetail(
                matrix_id=clause["matrix_id"],
                node_id=clause["section_id"] or "UNKNOWN",
                section_title=clause["section_title"] or "",
                type=clause["type"],
                actor=clause.get("actor"),
                action=clause.get("action"),
                object=clause.get("object"),
                condition=clause.get("condition"),
                deadline=clause.get("deadline"),
                metric=clause.get("metric"),
                original_text=clause["original_text"],
                page_number=clause["page_number"] or 0,
                image_caption=clause.get("image_caption"),
                table_caption=clause.get("table_caption"),
                positions=clause.get("positions", []),
            ))

        logger.info(f"Returning {len(result)} clauses (flat) for task {task_id}")
        return result

    finally:
        db.close()


@router.get("/clauses/search")
def search_clauses(
    keyword: str = Query(..., description="Search keyword"),
    task_id: Optional[str] = Query(None, description="Restrict to a specific task"),
    limit: int = Query(50, le=100, description="Maximum number of results"),
):
    """Search clauses by keyword, optionally within a single task."""
    db = get_db_session()
    try:
        clauses = ClauseRepository.search_clauses(
            db,
            keyword=keyword,
            task_id=task_id,
            limit=limit,
        )

        return [
            {
                "task_id": clause.task_id,
                "matrix_id": clause.matrix_id,
                "type": clause.clause_type,
                "original_text": clause.original_text[:200],
                "section_title": clause.section_title,
                "page_number": clause.page_number,
            }
            for clause in clauses
        ]
    finally:
        db.close()


# ============================================================================
# Backward-compatible aliases (deprecated paths)
# ============================================================================

@router.get("/tasks/{task_id}/requirements", response_model=List[ClauseSummary])
def get_task_requirements(task_id: str):
    """**Deprecated** – use ``/tasks/{task_id}/clauses`` instead."""
    return get_task_clauses(task_id)


@router.get("/tasks/{task_id}/requirements/all", response_model=List[ClauseDetail])
def get_all_requirements_flat(task_id: str):
    """**Deprecated** – use ``/tasks/{task_id}/clauses/all`` instead."""
    return get_all_clauses_flat(task_id)


@router.get("/requirements/search")
def search_requirements(
    keyword: str = Query(..., description="Search keyword"),
    task_id: Optional[str] = Query(None, description="Restrict to a specific task"),
    limit: int = Query(50, le=100, description="Maximum number of results"),
):
    """**Deprecated** – use ``/clauses/search`` instead."""
    return search_clauses(keyword, task_id, limit)
