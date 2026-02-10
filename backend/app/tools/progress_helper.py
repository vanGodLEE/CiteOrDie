"""
Progress reporting helpers.

Convenience wrappers around TaskTracker for pushing real-time progress
updates and step-level log entries from workflow nodes.
"""

from app.services.task_tracker import TaskTracker
from loguru import logger


def update_progress(task_id: str, progress: int, message: str, detail: str = None):
    """
    Push a progress update for the given task.

    The progress value is **monotonic**: if the proposed value is lower
    than the current one (e.g. due to parallel nodes updating
    concurrently), the message is still recorded but the percentage
    is clamped to the current high-water mark so the progress bar
    never moves backwards.

    Args:
        task_id: Task identifier (skip silently if None/empty).
        progress: Percentage complete (0-100).
        message: Primary status message.
        detail: Optional supplementary detail appended to *message*.
    """
    if not task_id:
        return

    full_message = f"{message} {detail}" if detail else message

    try:
        # Monotonic guard: never let progress decrease
        if progress is not None:
            task = TaskTracker.get_task(task_id)
            if task:
                current = task.get("progress", 0)
                if progress < current:
                    progress = current

        TaskTracker.update_task(
            task_id,
            progress=progress,
            message=full_message,
        )
        logger.info(f"[Progress {progress}%] {full_message}")
    except Exception as e:
        logger.warning(f"Failed to update progress: {e}")


def log_step(task_id: str, step_name: str, detail: str = ""):
    """
    Record a processing step without changing the progress percentage.

    Args:
        task_id: Task identifier (skip silently if None/empty).
        step_name: Human-readable step name.
        detail: Optional detail string.
    """
    if not task_id:
        return

    message = f"[Step] {step_name}" + (f": {detail}" if detail else "")

    try:
        TaskTracker.update_task(
            task_id,
            message=message,
        )
        logger.debug(message)
    except Exception as e:
        logger.warning(f"Failed to log step: {e}")
