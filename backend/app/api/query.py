"""
查询API

提供历史任务、日志、条款的查询接口
"""

from typing import List, Optional, Union
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from datetime import datetime
from loguru import logger

from app.db.database import get_db_session
from app.db.repositories import TaskRepository, TaskLogRepository, SectionRepository, ClauseRepository

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
    total_clauses: int
    total_requirements: int  # 向后兼容
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    elapsed_seconds: float


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
    total_clauses: int
    total_requirements: int  # 向后兼容
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    elapsed_seconds: float


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


class ClauseItem(BaseModel):
    """条款条目（简化版）"""
    matrix_id: str
    type: str
    actor: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    original_text: str
    section_title: str
    page_number: int


class ClauseDetail(BaseModel):
    """条款详情（包含节点ID和完整信息）"""
    matrix_id: str
    node_id: str  # 所在节点的ID（即section_id）
    section_title: str
    type: str  # 条款类型
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
    positions: List[List[Union[int, float]]] = []  # ✅ PDF坐标 [[page_idx(int), x0(float), y0(float), x1(float), y1(float)], ...]




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
                total_clauses=t.total_clauses or 0,
                total_requirements=t.total_requirements or 0,
                created_at=t.created_at,
                started_at=t.started_at,
                completed_at=t.completed_at,
                elapsed_seconds=t.elapsed_seconds or 0.0
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
            total_clauses=task.total_clauses or 0,
            total_requirements=task.total_requirements or 0,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            elapsed_seconds=task.elapsed_seconds or 0.0
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


@router.get("/tasks/{task_id}/clauses", response_model=List[ClauseItem])
def get_task_clauses(task_id: str):
    """获取任务提取的条款矩阵"""
    db = get_db_session()
    try:
        clauses = ClauseRepository.get_clauses(db, task_id)
        
        return [
            ClauseItem(
                matrix_id=clause.matrix_id,
                type=clause.clause_type,
                actor=clause.actor,
                action=clause.action,
                object=clause.object,
                original_text=clause.original_text,
                section_title=clause.section_title,
                page_number=clause.page_number
            )
            for clause in clauses
        ]
    finally:
        db.close()




@router.get("/tasks/{task_id}/clauses/all", response_model=List[ClauseDetail])
def get_all_clauses_flat(task_id: str):
    """
    获取任务的所有条款（扁平列表，按文档顺序）
    
    返回所有节点的条款，按页码从上到下排序，每个条款包含：
    - matrix_id: 条款唯一标识
    - node_id: 所在节点的ID（用于前端定位）
    - section_title: 章节标题
    - type: 条款类型
    - actor: 执行主体
    - action: 执行动作
    - object: 作用对象
    - condition: 触发条件
    - deadline: 时间要求
    - metric: 量化指标
    - original_text: 原文
    - page_number: 页码
    - image_caption: 图片描述（如果有）
    - table_caption: 表格描述（如果有）
    - positions: bbox坐标列表（页面坐标，左上角原点，单位points，前端需乘以scale后使用）
    
    适用于前端展示完整的条款列表和PDF标注
    
    重要：positions已在后端转换为实际页面坐标（左上原点），前端使用时只需：
    1. 计算scale: scale = containerWidth / viewport.width
    2. 应用scale: vx = x * scale, vy = y * scale
    3. 绘制高亮框: ctx.strokeRect(vx0, vy0, vx1-vx0, vy1-vy0)
    """
    db = get_db_session()
    try:
        # 验证任务是否存在
        task = TaskRepository.get_task(db, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # ✅ 使用新方法：直接获取带positions的条款（已解析JSON）
        clauses_data = ClauseRepository.get_clauses_with_positions(db, task_id)
        
        # positions已在保存时转换为页面坐标（左上角原点，单位points）
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
                positions=clause.get("positions", [])  # ✅ 已转换为页面坐标（左上原点，单位points，前端直接乘以scale使用）
            ))
        
        logger.info(f"返回任务 {task_id} 的 {len(result)} 条条款（扁平列表）")
        return result
        
    finally:
        db.close()




@router.get("/clauses/search")
def search_clauses(
    keyword: str = Query(..., description="搜索关键词"),
    task_id: Optional[str] = Query(None, description="限定任务ID"),
    limit: int = Query(50, le=100, description="返回数量限制")
):
    """
    搜索条款（支持关键词匹配）
    
    可用于跨任务搜索相似条款
    """
    db = get_db_session()
    try:
        clauses = ClauseRepository.search_clauses(
            db,
            keyword=keyword,
            task_id=task_id,
            limit=limit
        )
        
        return [
            {
                "task_id": clause.task_id,
                "matrix_id": clause.matrix_id,
                "type": clause.clause_type,
                "original_text": clause.original_text[:200],  # 截断原文
                "section_title": clause.section_title,
                "page_number": clause.page_number
            }
            for clause in clauses
        ]
    finally:
        db.close()


# ============================================================================
# 向后兼容接口（保留旧的 API 路径）
# ============================================================================

@router.get("/tasks/{task_id}/requirements", response_model=List[ClauseItem])
def get_task_requirements(task_id: str):
    """
    获取任务提取的条款矩阵（向后兼容接口）
    
    注意：此接口已废弃，请使用 /tasks/{task_id}/clauses
    内部实际调用 clause 接口
    """
    return get_task_clauses(task_id)


@router.get("/tasks/{task_id}/requirements/all", response_model=List[ClauseDetail])
def get_all_requirements_flat(task_id: str):
    """
    获取任务的所有条款（向后兼容接口）
    
    注意：此接口已废弃，请使用 /tasks/{task_id}/clauses/all
    内部实际调用 clause 接口
    """
    return get_all_clauses_flat(task_id)


@router.get("/requirements/search")
def search_requirements(
    keyword: str = Query(..., description="搜索关键词"),
    task_id: Optional[str] = Query(None, description="限定任务ID"),
    limit: int = Query(50, le=100, description="返回数量限制")
):
    """
    搜索条款（向后兼容接口）
    
    注意：此接口已废弃，请使用 /clauses/search
    内部实际调用 clause 接口
    """
    return search_clauses(keyword, task_id, limit)



