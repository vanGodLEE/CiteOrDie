"""
进度推送辅助工具

提供便捷的进度更新函数，用于在工作流各个节点中推送详细的实时进度
"""

from app.api.async_tasks import TaskManager
from loguru import logger


def update_progress(task_id: str, progress: int, message: str, detail: str = None):
    """
    更新任务进度（便捷函数）
    
    Args:
        task_id: 任务ID
        progress: 进度百分比 (0-100)
        message: 主要消息
        detail: 详细信息（可选）
    """
    if not task_id:
        return
    
    full_message = f"{message} {detail}" if detail else message
    
    try:
        TaskManager.update_task(
            task_id,
            progress=progress,
            message=full_message
        )
        logger.info(f"[进度 {progress}%] {full_message}")
    except Exception as e:
        logger.warning(f"更新进度失败: {e}")


def log_step(task_id: str, step_name: str, detail: str = ""):
    """
    记录处理步骤（不更新进度百分比，只推送日志）
    
    Args:
        task_id: 任务ID  
        step_name: 步骤名称
        detail: 详细信息
    """
    if not task_id:
        return
    
    message = f"  ▸ {step_name}" + (f": {detail}" if detail else "")
    
    try:
        TaskManager.update_task(
            task_id,
            message=message
        )
        logger.debug(message)
    except Exception as e:
        logger.warning(f"记录步骤失败: {e}")
