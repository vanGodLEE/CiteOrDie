"""
CRUD helpers (data-access layer).

Each repository class wraps SQLAlchemy operations for one ORM model and
exposes business-friendly static methods.
"""

import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from loguru import logger

from app.datasources.models import Task, TaskLog, Section, Clause


# ===========================================================================
# TaskRepository
# ===========================================================================

class TaskRepository:
    """Data-access helpers for :class:`Task`."""

    @staticmethod
    def create_task(
        db: Session,
        task_id: str,
        file_name: str,
        file_size: int = 0,
        pdf_path: str = "",
        file_hash: str = None,
        use_mock: bool = False,
    ) -> Task:
        """Insert a new task record."""
        task = Task(
            task_id=task_id,
            file_name=file_name,
            file_size=file_size,
            file_hash=file_hash,
            pdf_path=pdf_path,
            use_mock=1 if use_mock else 0,
            status="pending",
            created_at=datetime.now(),
        )
        db.add(task)
        db.commit()
        logger.info(f"DB: created task {task_id}")
        return task

    @staticmethod
    def update_task_status(
        db: Session,
        task_id: str,
        status: str = None,
        progress: float = None,
        message: str = None,
        error: str = None,
        elapsed_seconds: float = None,
        document_tree: dict = None,
        quality_report: dict = None,
    ) -> Optional[Task]:
        """Update task status and optionally store JSON results."""
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            logger.warning(f"Task {task_id} not found")
            return None

        if status:
            task.status = status
            if status == "running" and not task.started_at:
                task.started_at = datetime.now()
            elif status in ("completed", "failed"):
                task.completed_at = datetime.now()
                # Compute elapsed time if not explicitly provided
                if task.started_at and not elapsed_seconds:
                    elapsed_seconds = (task.completed_at - task.started_at).total_seconds()

        if progress is not None:
            task.progress = progress
        if message:
            task.current_message = message
        if error:
            task.error_message = error
        if elapsed_seconds is not None:
            task.elapsed_seconds = elapsed_seconds

        if document_tree is not None:
            task.document_tree_json = json.dumps(document_tree, ensure_ascii=False)
        if quality_report is not None:
            task.quality_report_json = json.dumps(quality_report, ensure_ascii=False)

        db.commit()
        return task

    @staticmethod
    def update_task_stats(
        db: Session,
        task_id: str,
        total_sections: int = None,
        total_clauses: int = None,
        total_requirements: int = None,  # DEPRECATED – kept for backward compat
    ) -> Optional[Task]:
        """Update aggregate statistics on a task."""
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            return None

        if total_sections is not None:
            task.total_sections = total_sections

        # Prefer total_clauses; fall back to total_requirements (compat)
        clauses_count = total_clauses if total_clauses is not None else total_requirements
        if clauses_count is not None:
            task.total_clauses = clauses_count
            task.total_requirements = clauses_count  # keep deprecated field in sync

        db.commit()
        return task

    @staticmethod
    def update_task(
        db: Session,
        task_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Task]:
        """Generic attribute update via a dict of field→value pairs."""
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            logger.warning(f"Task {task_id} not found")
            return None

        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)

        db.commit()
        logger.debug(f"DB: updated task {task_id}: {updates}")
        return task

    @staticmethod
    def get_task(db: Session, task_id: str) -> Optional[Task]:
        """Fetch a single task by ID."""
        return db.query(Task).filter(Task.task_id == task_id).first()

    @staticmethod
    def list_tasks(
        db: Session,
        status: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Task]:
        """List tasks, optionally filtered by status, newest first."""
        query = db.query(Task)
        if status:
            query = query.filter(Task.status == status)
        return query.order_by(Task.created_at.desc()).limit(limit).offset(offset).all()

    @staticmethod
    def delete_task(db: Session, task_id: str) -> bool:
        """
        Delete a task and all related records (cascade).

        Returns:
            ``True`` on success, ``False`` if the task was not found or
            an error occurred.
        """
        try:
            task = db.query(Task).filter(Task.task_id == task_id).first()
            if not task:
                logger.warning(f"Task not found: {task_id}")
                return False

            db.delete(task)
            db.commit()
            logger.info(f"DB: deleted task {task_id}")
            return True

        except Exception as e:
            logger.error(f"DB: failed to delete task: {e}")
            db.rollback()
            return False

    @staticmethod
    def find_by_file_hash(db: Session, file_hash: str) -> Optional[Task]:
        """
        Look up a task by file SHA-256 hash (idempotency check).

        Prefers a *completed* task; otherwise returns the most recent one.
        """
        if not file_hash:
            return None

        # 1. Prefer a completed task
        completed_task = db.query(Task).filter(
            Task.file_hash == file_hash,
            Task.status == "completed",
        ).order_by(Task.completed_at.desc()).first()

        if completed_task:
            logger.info(
                f"Found completed task: {completed_task.task_id} "
                f"(hash: {file_hash[:16]}...)"
            )
            return completed_task

        # 2. Fall back to most recent (may be running / failed)
        latest_task = db.query(Task).filter(
            Task.file_hash == file_hash,
        ).order_by(Task.created_at.desc()).first()

        if latest_task:
            logger.info(
                f"Found historical task: {latest_task.task_id} "
                f"[status: {latest_task.status}]"
            )

        return latest_task


# ===========================================================================
# TaskLogRepository
# ===========================================================================

class TaskLogRepository:
    """Data-access helpers for :class:`TaskLog`."""

    @staticmethod
    def add_log(
        db: Session,
        task_id: str,
        message: str,
        log_level: str = "info",
        progress: float = None,
    ) -> TaskLog:
        """Append a log entry for a task."""
        log = TaskLog(
            task_id=task_id,
            log_level=log_level,
            message=message,
            progress=progress,
            created_at=datetime.now(),
        )
        db.add(log)
        db.commit()
        return log

    @staticmethod
    def get_logs(db: Session, task_id: str) -> List[TaskLog]:
        """Return all log entries for a task, oldest first."""
        return db.query(TaskLog).filter(
            TaskLog.task_id == task_id,
        ).order_by(TaskLog.created_at.asc()).all()


# ===========================================================================
# SectionRepository
# ===========================================================================

class SectionRepository:
    """Data-access helpers for :class:`Section`."""

    @staticmethod
    def batch_create_sections(
        db: Session,
        task_id: str,
        sections_data: List[Dict[str, Any]],
    ) -> List[Section]:
        """Bulk-insert sections (with optional positions)."""
        sections: List[Section] = []
        for data in sections_data:
            positions = data.get("positions")
            positions_json = json.dumps(positions) if isinstance(positions, list) else None

            section = Section(
                task_id=task_id,
                section_id=data.get("section_id"),
                title=data.get("title"),
                reason=data.get("reason"),
                priority=data.get("priority"),
                start_page=data.get("start_page"),
                end_page=data.get("end_page"),
                start_index=data.get("start_index"),
                positions_json=positions_json,
                created_at=datetime.now(),
            )
            sections.append(section)

        db.add_all(sections)
        db.commit()
        logger.info(f"DB: saved {len(sections)} sections")
        return sections

    @staticmethod
    def get_sections(db: Session, task_id: str) -> List[Section]:
        """Return all sections for a task, ordered by priority."""
        return db.query(Section).filter(
            Section.task_id == task_id,
        ).order_by(Section.priority).all()


# ===========================================================================
# ClauseRepository
# ===========================================================================

class ClauseRepository:
    """Data-access helpers for :class:`Clause`."""

    @staticmethod
    def batch_create_clauses(
        db: Session,
        task_id: str,
        clauses_data: List[Dict[str, Any]],
    ) -> List[Clause]:
        """Bulk-insert clauses (with optional positions)."""
        clauses: List[Clause] = []
        for data in clauses_data:
            positions = data.get("positions")
            positions_json = json.dumps(positions) if isinstance(positions, list) else None

            clause = Clause(
                task_id=task_id,
                matrix_id=data.get("matrix_id"),
                section_id=data.get("section_id"),
                section_title=data.get("section_title"),
                page_number=data.get("page_number"),
                clause_type=data.get("type", "requirement"),
                actor=data.get("actor"),
                action=data.get("action"),
                object=data.get("object"),
                condition=data.get("condition"),
                deadline=data.get("deadline"),
                metric=data.get("metric"),
                original_text=data.get("original_text"),
                image_caption=data.get("image_caption"),
                table_caption=data.get("table_caption"),
                positions_json=positions_json,
                created_at=datetime.now(),
            )
            clauses.append(clause)

        db.add_all(clauses)
        db.commit()
        logger.info(f"DB: saved {len(clauses)} clauses")
        return clauses

    @staticmethod
    def get_clauses(db: Session, task_id: str) -> List[Clause]:
        """Return all clauses for a task, ordered by page then ID."""
        return db.query(Clause).filter(
            Clause.task_id == task_id,
        ).order_by(Clause.page_number, Clause.id).all()

    @staticmethod
    def get_clauses_with_positions(db: Session, task_id: str) -> List[Dict[str, Any]]:
        """
        Return clauses as dicts with ``positions`` decoded from JSON.
        """
        clauses = ClauseRepository.get_clauses(db, task_id)

        result: List[Dict[str, Any]] = []
        for clause in clauses:
            clause_dict: Dict[str, Any] = {
                "id": clause.id,
                "matrix_id": clause.matrix_id,
                "section_id": clause.section_id,
                "section_title": clause.section_title,
                "page_number": clause.page_number,
                "type": clause.clause_type,
                "actor": clause.actor,
                "action": clause.action,
                "object": clause.object,
                "condition": clause.condition,
                "deadline": clause.deadline,
                "metric": clause.metric,
                "original_text": clause.original_text,
                "image_caption": clause.image_caption,
                "table_caption": clause.table_caption,
                "positions": [],
            }

            if clause.positions_json:
                try:
                    clause_dict["positions"] = json.loads(clause.positions_json)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse positions_json for clause {clause.matrix_id}"
                    )

            result.append(clause_dict)

        return result

    @staticmethod
    def search_clauses(
        db: Session,
        keyword: str,
        task_id: str = None,
        limit: int = 50,
    ) -> List[Clause]:
        """Simple keyword search across clause original text."""
        query = db.query(Clause).filter(
            Clause.original_text.like(f"%{keyword}%"),
        )
        if task_id:
            query = query.filter(Clause.task_id == task_id)
        return query.limit(limit).all()
