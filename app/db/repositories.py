"""
数据访问层（Repository）

封装数据库CRUD操作，提供业务友好的接口
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from loguru import logger

from app.db.models import Task, TaskLog, Section, Requirement


class TaskRepository:
    """任务数据访问"""
    
    @staticmethod
    def create_task(
        db: Session,
        task_id: str,
        file_name: str,
        file_size: int = 0,
        pdf_path: str = "",
        use_mock: bool = False
    ) -> Task:
        """创建新任务"""
        task = Task(
            task_id=task_id,
            file_name=file_name,
            file_size=file_size,
            pdf_path=pdf_path,
            use_mock=1 if use_mock else 0,
            status="pending",
            created_at=datetime.now()
        )
        db.add(task)
        db.commit()
        logger.info(f"数据库：创建任务 {task_id}")
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
        document_tree: dict = None
    ) -> Optional[Task]:
        """更新任务状态"""
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            logger.warning(f"任务 {task_id} 不存在")
            return None
        
        if status:
            task.status = status
            if status == "running" and not task.started_at:
                task.started_at = datetime.now()
            elif status in ["completed", "failed"]:
                task.completed_at = datetime.now()
                # 计算最终耗时（如果有开始时间）
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
        
        # 保存document_tree（JSON序列化）
        if document_tree is not None:
            import json
            task.document_tree_json = json.dumps(document_tree, ensure_ascii=False)
        
        db.commit()
        return task
    
    @staticmethod
    def update_task_stats(
        db: Session,
        task_id: str,
        total_sections: int = None,
        total_requirements: int = None
    ) -> Optional[Task]:
        """更新任务统计信息"""
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            return None
        
        if total_sections is not None:
            task.total_sections = total_sections
        
        if total_requirements is not None:
            task.total_requirements = total_requirements
        
        db.commit()
        return task
    
    @staticmethod
    def update_task(
        db: Session,
        task_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Task]:
        """通用任务更新方法"""
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            logger.warning(f"任务 {task_id} 不存在")
            return None
        
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)
        
        db.commit()
        logger.debug(f"更新任务 {task_id}: {updates}")
        return task
    
    @staticmethod
    def get_task(db: Session, task_id: str) -> Optional[Task]:
        """获取任务"""
        return db.query(Task).filter(Task.task_id == task_id).first()
    
    @staticmethod
    def list_tasks(
        db: Session,
        status: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Task]:
        """列出任务"""
        query = db.query(Task)
        if status:
            query = query.filter(Task.status == status)
        return query.order_by(Task.created_at.desc()).limit(limit).offset(offset).all()


class TaskLogRepository:
    """任务日志数据访问"""
    
    @staticmethod
    def add_log(
        db: Session,
        task_id: str,
        message: str,
        log_level: str = "info",
        progress: float = None
    ) -> TaskLog:
        """添加日志"""
        log = TaskLog(
            task_id=task_id,
            log_level=log_level,
            message=message,
            progress=progress,
            created_at=datetime.now()
        )
        db.add(log)
        db.commit()
        # 不需要refresh，避免跨线程访问已提交的对象
        return log
    
    @staticmethod
    def get_logs(db: Session, task_id: str) -> List[TaskLog]:
        """获取任务的所有日志"""
        return db.query(TaskLog).filter(
            TaskLog.task_id == task_id
        ).order_by(TaskLog.created_at.asc()).all()


class SectionRepository:
    """章节数据访问"""
    
    @staticmethod
    def batch_create_sections(
        db: Session,
        task_id: str,
        sections_data: List[Dict[str, Any]]
    ) -> List[Section]:
        """批量创建章节"""
        sections = []
        for data in sections_data:
            section = Section(
                task_id=task_id,
                section_id=data.get("section_id"),
                title=data.get("title"),
                reason=data.get("reason"),
                priority=data.get("priority"),
                start_page=data.get("start_page"),
                end_page=data.get("end_page"),
                start_index=data.get("start_index"),
                created_at=datetime.now()
            )
            sections.append(section)
        
        db.add_all(sections)
        db.commit()
        logger.info(f"数据库：保存 {len(sections)} 个章节")
        return sections
    
    @staticmethod
    def get_sections(db: Session, task_id: str) -> List[Section]:
        """获取任务的所有章节"""
        return db.query(Section).filter(
            Section.task_id == task_id
        ).order_by(Section.priority).all()


class RequirementRepository:
    """需求数据访问"""
    
    @staticmethod
    def batch_create_requirements(
        db: Session,
        task_id: str,
        requirements_data: List[Dict[str, Any]]
    ) -> List[Requirement]:
        """批量创建需求"""
        requirements = []
        for data in requirements_data:
            req = Requirement(
                task_id=task_id,
                matrix_id=data.get("matrix_id"),
                section_id=data.get("section_id"),
                section_title=data.get("section_title"),
                page_number=data.get("page_number"),
                requirement=data.get("requirement"),
                original_text=data.get("original_text"),
                response_suggestion=data.get("response_suggestion"),
                risk_warning=data.get("risk_warning"),
                notes=data.get("notes"),
                created_at=datetime.now()
            )
            requirements.append(req)
        
        db.add_all(requirements)
        db.commit()
        logger.info(f"数据库：保存 {len(requirements)} 条需求")
        return requirements
    
    @staticmethod
    def get_requirements(db: Session, task_id: str) -> List[Requirement]:
        """获取任务的所有需求"""
        return db.query(Requirement).filter(
            Requirement.task_id == task_id
        ).order_by(Requirement.page_number, Requirement.id).all()
    
    @staticmethod
    def search_requirements(
        db: Session,
        keyword: str,
        task_id: str = None,
        limit: int = 50
    ) -> List[Requirement]:
        """搜索需求（简单关键词匹配）"""
        query = db.query(Requirement).filter(
            Requirement.requirement.like(f"%{keyword}%")
        )
        
        if task_id:
            query = query.filter(Requirement.task_id == task_id)
        
        return query.limit(limit).all()

