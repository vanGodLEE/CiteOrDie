"""
查询API

提供历史任务、日志、需求的查询接口
"""

from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from datetime import datetime
from loguru import logger

from app.db.database import get_db_session
from app.db.repositories import TaskRepository, TaskLogRepository, SectionRepository, RequirementRepository

router = APIRouter(prefix="/api")


# ============================================================================
# 响应模型
# ============================================================================

class TaskSummary(BaseModel):
    """任务摘要"""
    task_id: str
    file_name: str
    status: str
    progress: float
    total_sections: int
    total_requirements: int
    created_at: datetime
    completed_at: Optional[datetime]


class TaskDetail(BaseModel):
    """任务详情"""
    task_id: str
    file_name: str
    file_size: int
    status: str
    progress: float
    current_message: Optional[str]
    error_message: Optional[str]
    total_sections: int
    total_requirements: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class LogItem(BaseModel):
    """日志条目"""
    id: int
    log_level: str
    progress: Optional[float]
    message: str
    created_at: datetime


class SectionItem(BaseModel):
    """章节条目"""
    section_id: str
    title: str
    reason: Optional[str]
    priority: int
    start_page: int


class RequirementItem(BaseModel):
    """需求条目"""
    matrix_id: str
    requirement: str
    original_text: str
    section_title: str
    page_number: int
    response_suggestion: str
    risk_warning: str
    notes: str


# ============================================================================
# API端点
# ============================================================================

@router.get("/tasks", response_model=List[TaskSummary])
def list_tasks(
    status: Optional[str] = Query(None, description="任务状态筛选"),
    limit: int = Query(50, le=100, description="返回数量限制"),
    offset: int = Query(0, description="偏移量")
):
    """
    获取任务列表
    
    支持按状态筛选和分页
    """
    db = get_db_session()
    try:
        tasks = TaskRepository.list_tasks(db, status=status, limit=limit, offset=offset)
        
        result = [
            TaskSummary(
                task_id=t.task_id,
                file_name=t.file_name,
                status=t.status,
                progress=t.progress,
                total_sections=t.total_sections,
                total_requirements=t.total_requirements,
                created_at=t.created_at,
                completed_at=t.completed_at
            )
            for t in tasks
        ]
        
        return result
    finally:
        db.close()


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task_detail(task_id: str):
    """获取任务详情"""
    db = get_db_session()
    try:
        task = TaskRepository.get_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return TaskDetail(
            task_id=task.task_id,
            file_name=task.file_name,
            file_size=task.file_size,
            status=task.status,
            progress=task.progress,
            current_message=task.current_message,
            error_message=task.error_message,
            total_sections=task.total_sections,
            total_requirements=task.total_requirements,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at
        )
    finally:
        db.close()


@router.get("/tasks/{task_id}/logs", response_model=List[LogItem])
def get_task_logs(task_id: str):
    """获取任务的执行日志（用于复盘）"""
    db = get_db_session()
    try:
        logs = TaskLogRepository.get_logs(db, task_id)
        
        return [
            LogItem(
                id=log.id,
                log_level=log.log_level,
                progress=log.progress,
                message=log.message,
                created_at=log.created_at
            )
            for log in logs
        ]
    finally:
        db.close()


@router.get("/tasks/{task_id}/sections", response_model=List[SectionItem])
def get_task_sections(task_id: str):
    """获取任务筛选出的章节"""
    db = get_db_session()
    try:
        sections = SectionRepository.get_sections(db, task_id)
        
        return [
            SectionItem(
                section_id=sec.section_id,
                title=sec.title,
                reason=sec.reason,
                priority=sec.priority,
                start_page=sec.start_page
            )
            for sec in sections
        ]
    finally:
        db.close()


@router.get("/tasks/{task_id}/requirements", response_model=List[RequirementItem])
def get_task_requirements(task_id: str):
    """获取任务提取的需求矩阵"""
    db = get_db_session()
    try:
        requirements = RequirementRepository.get_requirements(db, task_id)
        
        return [
            RequirementItem(
                matrix_id=req.matrix_id,
                requirement=req.requirement,
                original_text=req.original_text,
                section_title=req.section_title,
                page_number=req.page_number,
                response_suggestion=req.response_suggestion,
                risk_warning=req.risk_warning,
                notes=req.notes
            )
            for req in requirements
        ]
    finally:
        db.close()


@router.get("/requirements/search")
def search_requirements(
    keyword: str = Query(..., description="搜索关键词"),
    task_id: Optional[str] = Query(None, description="限定任务ID"),
    limit: int = Query(50, le=100, description="返回数量限制")
):
    """
    搜索需求（支持关键词匹配）
    
    可用于跨任务搜索相似需求
    """
    db = get_db_session()
    try:
        requirements = RequirementRepository.search_requirements(
            db,
            keyword=keyword,
            task_id=task_id,
            limit=limit
        )
        
        return [
            {
                "task_id": req.task_id,
                "matrix_id": req.matrix_id,
                "requirement": req.requirement,
                "original_text": req.original_text[:200],  # 截断原文
                "section_title": req.section_title,
                "page_number": req.page_number
            }
            for req in requirements
        ]
    finally:
        db.close()

