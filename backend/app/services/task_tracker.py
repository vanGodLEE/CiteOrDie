"""
Task lifecycle tracker (dual-storage).

Tracks long-running analysis tasks with two complementary stores:

* **In-memory cache** (``_task_cache``) – fast lookups for SSE streaming
  and real-time progress updates.
* **SQLite** (via :mod:`app.db.crud`) – persistence across process restarts.

All public methods are ``@staticmethod`` so callers can use them without
instantiation (the cache is module-level state).
"""

import uuid
from datetime import datetime
from typing import Dict, Optional

from loguru import logger
from pydantic import BaseModel

from app.datasources.crud import TaskLogRepository, TaskRepository
from app.datasources.database import get_db_session

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_task_cache: Dict[str, dict] = {}
"""In-memory task state, keyed by ``task_id``."""

_MAX_LOG_ENTRIES = 50
"""Maximum in-memory log entries kept per task (ring-buffer)."""


# ---------------------------------------------------------------------------
# Snapshot model
# ---------------------------------------------------------------------------

class TaskStatus(BaseModel):
    """Serialisable snapshot of a task's current state."""

    task_id: str
    status: str                         # pending | running | completed | failed
    progress: float                     # 0–100
    message: str
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    start_time: Optional[datetime] = None
    elapsed_seconds: float = 0
    logs: list = []                     # recent log entries (capped)


# ---------------------------------------------------------------------------
# TaskTracker
# ---------------------------------------------------------------------------

class TaskTracker:
    """
    Dual-storage task lifecycle tracker.

    Maintains an in-memory cache for fast reads (SSE streaming) and
    writes through to SQLite for persistence.  Database failures are
    logged but never propagated – the in-memory state is authoritative
    during a process's lifetime.
    """

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    def create_task(
        task_id: str = None,
        file_name: str = "unknown",
        file_size: int = 0,
        pdf_path: str = "",
        file_hash: str = None,
        use_mock: bool = False,
    ) -> str:
        """Create a new task and persist it to the database.

        Returns:
            The (possibly auto-generated) ``task_id``.
        """
        if task_id is None:
            task_id = str(uuid.uuid4())

        now = datetime.now()
        _task_cache[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0,
            "message": "Task created",
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "start_time": None,
            "elapsed_seconds": 0,
            "logs": [],
        }

        try:
            db = get_db_session()
            TaskRepository.create_task(
                db,
                task_id=task_id,
                file_name=file_name,
                file_size=file_size,
                pdf_path=pdf_path,
                file_hash=file_hash,
                use_mock=use_mock,
            )
            db.close()
        except Exception as e:
            logger.error(f"DB write failed while creating task: {e}")

        hash_preview = file_hash[:16] if file_hash else "N/A"
        logger.info(f"Task created: {task_id} (hash: {hash_preview}...)")
        return task_id

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @staticmethod
    def update_task(
        task_id: str,
        status: str = None,
        progress: float = None,
        message: str = None,
        result: dict = None,
        error: str = None,
        document_tree: dict = None,
        quality_report: dict = None,
    ) -> None:
        """Update task state in-memory and persist to the database.

        Database write failures are logged but do not raise – the
        in-memory state remains the source of truth for the current
        process lifetime.
        """
        if task_id not in _task_cache:
            logger.warning(f"Task not found in cache: {task_id}")
            return

        task = _task_cache[task_id]
        now = datetime.now()

        # Record start time on first transition to "running"
        if status == "running" and task.get("start_time") is None:
            task["start_time"] = now
            logger.info(f"Task started: {task_id}")

        # Elapsed time
        if task.get("start_time"):
            task["elapsed_seconds"] = (now - task["start_time"]).total_seconds()

        if status:
            task["status"] = status
        if progress is not None:
            task["progress"] = progress
        if message:
            task["message"] = message
            task["logs"].append({
                "timestamp": now.strftime("%H:%M:%S"),
                "message": message,
                "progress": progress if progress is not None else task.get("progress", 0),
            })
            if len(task["logs"]) > _MAX_LOG_ENTRIES:
                task["logs"] = task["logs"][-_MAX_LOG_ENTRIES:]
        if result is not None:
            task["result"] = result
        if error:
            task["error"] = error

        task["updated_at"] = now

        # Persist to database (failure must not block the main flow)
        try:
            db = get_db_session()
            try:
                TaskRepository.update_task_status(
                    db,
                    task_id=task_id,
                    status=status,
                    progress=progress,
                    message=message,
                    error=error,
                    elapsed_seconds=task.get("elapsed_seconds"),
                    document_tree=document_tree,
                    quality_report=quality_report,
                )
                if message:
                    log_level = (
                        "error" if error
                        else ("warning" if status == "failed" else "info")
                    )
                    TaskLogRepository.add_log(
                        db,
                        task_id=task_id,
                        message=message,
                        log_level=log_level,
                        progress=progress,
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"DB write failed (task unaffected): {e}")

        logger.debug(f"Task updated: {task_id} – {status} – {progress}% – {message}")

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @staticmethod
    def get_task(task_id: str) -> Optional[dict]:
        """Return task state, checking cache first then the database.

        If recovered from the database the task is cached for subsequent
        lookups.
        """
        if task_id in _task_cache:
            return _task_cache[task_id]

        # Attempt recovery from database
        try:
            db = get_db_session()
            try:
                record = TaskRepository.get_task(db, task_id)
                if not record:
                    return None

                task_dict = {
                    "task_id": record.task_id,
                    "status": record.status,
                    "progress": record.progress,
                    "message": record.current_message or "",
                    "result": None,
                    "error": record.error_message,
                    "created_at": record.created_at,
                    "updated_at": (
                        record.completed_at
                        or record.started_at
                        or record.created_at
                    ),
                    "start_time": record.started_at,
                    "elapsed_seconds": record.elapsed_seconds or 0,
                    "logs": [],
                }

                _task_cache[task_id] = task_dict
                logger.info(f"Task recovered from DB: {task_id}")
                return task_dict
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to recover task from DB: {e}")
            return None

    @staticmethod
    def log_progress(task_id: str, message: str, progress: float = None) -> None:
        """Convenience wrapper: update progress and message."""
        TaskTracker.update_task(task_id=task_id, progress=progress, message=message)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    @staticmethod
    def delete_task(task_id: str) -> None:
        """Remove the task from the in-memory cache (DB record kept)."""
        if task_id in _task_cache:
            del _task_cache[task_id]
            logger.info(f"Task cache cleared: {task_id}")

    @staticmethod
    def load_completed_task(task_id: str) -> None:
        """Load a completed task from the database into the cache.

        Used for idempotency: when the same file is uploaded again the
        historical task must be in memory so the frontend can subscribe
        to SSE and query results.
        """
        if task_id in _task_cache:
            logger.debug(f"Task already in cache: {task_id}")
            return

        try:
            db = get_db_session()
            try:
                record = TaskRepository.get_task(db, task_id)
                if not record:
                    logger.warning(f"Task not found in DB: {task_id}")
                    return

                _task_cache[task_id] = {
                    "task_id": record.task_id,
                    "status": record.status,
                    "progress": record.progress,
                    "message": record.current_message or "Task completed",
                    "result": None,
                    "error": record.error_message,
                    "created_at": record.created_at,
                    "updated_at": record.completed_at or record.created_at,
                    "start_time": record.started_at,
                    "elapsed_seconds": record.elapsed_seconds or 0,
                    "logs": [],
                }

                logger.info(
                    f"Task loaded into cache: {task_id} "
                    f"[status: {record.status}]"
                )
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to load task: {e}")


# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------

TaskManager = TaskTracker
