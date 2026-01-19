"""
数据访问层（Repository）

封装数据库CRUD操作，提供业务友好的接口
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from loguru import logger

from app.db.models import Task, TaskLog, Section, Clause


class TaskRepository:
    """任务数据访问"""
    
    @staticmethod
    def create_task(
        db: Session,
        task_id: str,
        file_name: str,
        file_size: int = 0,
        pdf_path: str = "",
        file_hash: str = None,
        use_mock: bool = False
    ) -> Task:
        """创建新任务"""
        task = Task(
            task_id=task_id,
            file_name=file_name,
            file_size=file_size,
            file_hash=file_hash,
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
        total_clauses: int = None,
        total_requirements: int = None  # 向后兼容
    ) -> Optional[Task]:
        """更新任务统计信息"""
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if not task:
            return None
        
        if total_sections is not None:
            task.total_sections = total_sections
        
        # 优先使用 total_clauses，如果没有则使用 total_requirements（向后兼容）
        clauses_count = total_clauses if total_clauses is not None else total_requirements
        if clauses_count is not None:
            task.total_clauses = clauses_count
            task.total_requirements = clauses_count  # 同时更新向后兼容字段
        
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
    
    @staticmethod
    def find_by_file_hash(db: Session, file_hash: str) -> Optional[Task]:
        """
        根据文件哈希查找任务（用于幂等性检查）
        
        优先返回状态为 completed 的任务
        如果没有 completed 任务，返回最新的任务
        
        Args:
            db: 数据库会话
            file_hash: 文件SHA256哈希值
            
        Returns:
            Task对象或None
        """
        if not file_hash:
            return None
        
        # 1. 优先查找已完成的任务
        completed_task = db.query(Task).filter(
            Task.file_hash == file_hash,
            Task.status == "completed"
        ).order_by(Task.completed_at.desc()).first()
        
        if completed_task:
            logger.info(f"找到已完成的任务: {completed_task.task_id} (文件哈希: {file_hash[:16]}...)")
            return completed_task
        
        # 2. 如果没有已完成的，返回最新的任务（可能正在运行或失败）
        latest_task = db.query(Task).filter(
            Task.file_hash == file_hash
        ).order_by(Task.created_at.desc()).first()
        
        if latest_task:
            logger.info(f"找到历史任务: {latest_task.task_id} [状态: {latest_task.status}]")
        
        return latest_task


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
        """批量创建章节（支持positions）"""
        import json
        sections = []
        for data in sections_data:
            # ✅ 处理positions：如果是list，转为JSON字符串
            positions = data.get("positions")
            positions_json = None
            if positions and isinstance(positions, list):
                positions_json = json.dumps(positions)
            
            section = Section(
                task_id=task_id,
                section_id=data.get("section_id"),
                title=data.get("title"),
                reason=data.get("reason"),
                priority=data.get("priority"),
                start_page=data.get("start_page"),
                end_page=data.get("end_page"),
                start_index=data.get("start_index"),
                positions_json=positions_json,  # ✅ 保存positions
                created_at=datetime.now()
            )
            sections.append(section)
        
        db.add_all(sections)
        db.commit()
        logger.info(f"数据库：保存 {len(sections)} 个章节（含positions）")
        return sections
    
    @staticmethod
    def get_sections(db: Session, task_id: str) -> List[Section]:
        """获取任务的所有章节"""
        return db.query(Section).filter(
            Section.task_id == task_id
        ).order_by(Section.priority).all()


class ClauseRepository:
    """条款数据访问"""
    
    @staticmethod
    def batch_create_clauses(
        db: Session,
        task_id: str,
        clauses_data: List[Dict[str, Any]]
    ) -> List[Clause]:
        """批量创建条款（支持positions）"""
        import json
        clauses = []
        for data in clauses_data:
            # ✅ 处理positions：如果是list，转为JSON字符串
            positions = data.get("positions")
            positions_json = None
            if positions and isinstance(positions, list):
                positions_json = json.dumps(positions)
            
            clause = Clause(
                task_id=task_id,
                matrix_id=data.get("matrix_id"),
                section_id=data.get("section_id"),
                section_title=data.get("section_title"),
                page_number=data.get("page_number"),
                clause_type=data.get("type", "requirement"),  # 新字段
                actor=data.get("actor"),  # 新字段
                action=data.get("action"),  # 新字段
                object=data.get("object"),  # 新字段
                condition=data.get("condition"),  # 新字段
                deadline=data.get("deadline"),  # 新字段
                metric=data.get("metric"),  # 新字段
                original_text=data.get("original_text"),
                image_caption=data.get("image_caption"),
                table_caption=data.get("table_caption"),
                positions_json=positions_json,  # ✅ 保存positions
                created_at=datetime.now()
            )
            clauses.append(clause)
        
        db.add_all(clauses)
        db.commit()
        logger.info(f"数据库：保存 {len(clauses)} 条条款（含positions）")
        return clauses
    
    @staticmethod
    def get_clauses(db: Session, task_id: str) -> List[Clause]:
        """获取任务的所有条款（按文档顺序排列）"""
        return db.query(Clause).filter(
            Clause.task_id == task_id
        ).order_by(Clause.page_number, Clause.id).all()
    
    @staticmethod
    def get_clauses_with_positions(db: Session, task_id: str) -> List[Dict[str, Any]]:
        """
        获取任务的所有条款（含positions，解析为字典）
        
        返回字典列表，positions字段已从JSON解析为Python list
        """
        import json
        clauses = ClauseRepository.get_clauses(db, task_id)
        
        result = []
        for clause in clauses:
            clause_dict = {
                "id": clause.id,
                "matrix_id": clause.matrix_id,
                "section_id": clause.section_id,
                "section_title": clause.section_title,
                "page_number": clause.page_number,
                "type": clause.clause_type,  # 新字段
                "actor": clause.actor,  # 新字段
                "action": clause.action,  # 新字段
                "object": clause.object,  # 新字段
                "condition": clause.condition,  # 新字段
                "deadline": clause.deadline,  # 新字段
                "metric": clause.metric,  # 新字段
                "original_text": clause.original_text,
                "image_caption": clause.image_caption,
                "table_caption": clause.table_caption,
                "positions": []  # 默认空列表
            }
            
            # ✅ 解析positions_json
            if clause.positions_json:
                try:
                    clause_dict["positions"] = json.loads(clause.positions_json)
                except json.JSONDecodeError:
                    logger.warning(f"条款 {clause.matrix_id} 的positions_json解析失败")
            
            result.append(clause_dict)
        
        return result
    
    @staticmethod
    def search_clauses(
        db: Session,
        keyword: str,
        task_id: str = None,
        limit: int = 50
    ) -> List[Clause]:
        """搜索条款（简单关键词匹配）"""
        query = db.query(Clause).filter(
            Clause.original_text.like(f"%{keyword}%")
        )
        
        if task_id:
            query = query.filter(Clause.task_id == task_id)
        
        return query.limit(limit).all()



