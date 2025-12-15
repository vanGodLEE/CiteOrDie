"""
异步任务处理

支持长时间运行的任务（如PDF解析），实时推送进度到前端
同时持久化到SQLite数据库
"""

import uuid
import asyncio
from typing import Dict, Optional
from datetime import datetime
from pydantic import BaseModel
from loguru import logger

from app.db.database import get_db_session
from app.db.repositories import TaskRepository, TaskLogRepository

# 任务状态存储（内存缓存，用于SSE推送）
task_store: Dict[str, dict] = {}


class TaskStatus(BaseModel):
    """任务状态"""
    task_id: str
    status: str  # pending, running, completed, failed
    progress: float  # 0-100
    message: str
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    start_time: Optional[datetime] = None  # 开始时间
    elapsed_seconds: float = 0  # 消耗时间（秒）
    logs: list = []  # 实时日志列表


class TaskManager:
    """
    任务管理器
    
    双重存储策略：
    1. 内存存储（task_store）- 用于SSE推送，快速访问
    2. SQLite持久化 - 用于历史记录、复盘分析
    """
    
    @staticmethod
    def create_task(
        task_id: str = None,
        file_name: str = "unknown",
        file_size: int = 0,
        pdf_path: str = "",
        use_mock: bool = False
    ) -> str:
        """创建新任务"""
        if task_id is None:
            task_id = str(uuid.uuid4())
        
        # 内存存储
        now = datetime.now()
        task_store[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0,
            "message": "任务已创建",
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "start_time": None,  # 开始时间（状态变为running时设置）
            "elapsed_seconds": 0,
            "logs": []  # 日志列表，最多保留50条
        }
        
        # 数据库持久化
        try:
            db = get_db_session()
            TaskRepository.create_task(
                db,
                task_id=task_id,
                file_name=file_name,
                file_size=file_size,
                pdf_path=pdf_path,
                use_mock=use_mock
            )
            db.close()
        except Exception as e:
            logger.error(f"创建任务时数据库写入失败: {e}")
        
        logger.info(f"创建任务: {task_id}")
        return task_id
    
    @staticmethod
    def update_task(
        task_id: str,
        status: str = None,
        progress: float = None,
        message: str = None,
        result: dict = None,
        error: str = None
    ):
        """更新任务状态"""
        if task_id not in task_store:
            logger.warning(f"任务不存在（内存）: {task_id}")
            return
        
        # 更新内存存储
        task = task_store[task_id]
        now = datetime.now()
        
        # 状态变更为running时，记录开始时间
        if status == "running" and task.get("start_time") is None:
            task["start_time"] = now
            logger.info(f"任务开始: {task_id}")
        
        # 计算消耗时间
        if task.get("start_time"):
            task["elapsed_seconds"] = (now - task["start_time"]).total_seconds()
        
        if status:
            task["status"] = status
        if progress is not None:
            task["progress"] = progress
        if message:
            task["message"] = message
            # 添加到日志列表（带时间戳）
            log_entry = {
                "timestamp": now.strftime("%H:%M:%S"),
                "message": message,
                "progress": progress if progress is not None else task.get("progress", 0)
            }
            task["logs"].append(log_entry)
            # 最多保留最近50条日志
            if len(task["logs"]) > 50:
                task["logs"] = task["logs"][-50:]
        
        if result is not None:
            task["result"] = result
        if error:
            task["error"] = error
        
        task["updated_at"] = now
        
        # 更新数据库（异步，不阻塞主流程）
        # 使用独立Session，避免跨线程共享
        try:
            db = get_db_session()
            try:
                # 更新任务状态
                TaskRepository.update_task_status(
                    db,
                    task_id=task_id,
                    status=status,
                    progress=progress,
                    message=message,
                    error=error
                )
                
                # 记录日志（用于复盘）
                if message:
                    log_level = "error" if error else ("warning" if status == "failed" else "info")
                    TaskLogRepository.add_log(
                        db,
                        task_id=task_id,
                        message=message,
                        log_level=log_level,
                        progress=progress
                    )
            finally:
                # 确保Session关闭
                db.close()
        except Exception as e:
            # 数据库写入失败不应影响主流程
            logger.warning(f"数据库写入失败（不影响任务执行）: {e}")
        
        logger.debug(f"任务更新: {task_id} - {status} - {progress}% - {message}")
    
    @staticmethod
    def get_task(task_id: str) -> Optional[dict]:
        """获取任务状态（从内存）"""
        return task_store.get(task_id)
    
    @staticmethod
    def log_progress(task_id: str, message: str, progress: float = None):
        """
        记录任务进度日志（便捷方法）
        """
        TaskManager.update_task(
            task_id=task_id,
            progress=progress,
            message=message
        )
    
    @staticmethod
    def delete_task(task_id: str):
        """删除任务（仅清理内存，保留数据库记录）"""
        if task_id in task_store:
            del task_store[task_id]
            logger.info(f"清理任务缓存: {task_id}")

