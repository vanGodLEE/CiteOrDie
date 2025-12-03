"""
异步分析API - 支持SSE进度推送
基于PageIndex的PDF文档分析
"""

import json
import asyncio
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, File, UploadFile, BackgroundTasks
from fastapi.responses import StreamingResponse
from loguru import logger

from app.api.async_tasks import TaskManager
from app.core.graph import create_tender_analysis_graph
from app.core.states import TenderAnalysisState

router = APIRouter()


async def run_analysis_task(task_id: str, pdf_path: str):
    """
    后台任务：执行分析流程
    """
    try:
        # 更新状态：开始运行
        TaskManager.update_task(
            task_id,
            status="running",
            progress=0,
            message="开始分析..."
        )
        
        # 创建初始状态
        initial_state = TenderAnalysisState(
            pdf_path=pdf_path,
            use_mock=False,
            task_id=task_id,
            pageindex_document=None,
            content_list=[],
            markdown="",
            toc=[],
            toc_tree=None,
            target_sections=[],
            requirements=[],
            final_matrix=[],
            processing_start_time=None,
            processing_end_time=None,
            error_message=None
        )
        
        # 创建工作流图
        graph = create_tender_analysis_graph()
        
        # 在后台线程中执行
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, graph.invoke, initial_state)
        
        # 检查是否有错误
        if result.get("error_message"):
            raise Exception(result["error_message"])
        
        # 获取最终结果
        final_matrix = result.get("final_matrix", [])
        pageindex_doc = result.get("pageindex_document")
        
        # 保存到数据库
        from app.db.repositories import (
            TaskRepository, 
            SectionRepository, 
            RequirementRepository
        )
        from app.db.database import SessionLocal
        
        db = SessionLocal()
        try:
            # 批量保存章节信息（从PageIndex的叶子节点）
            if pageindex_doc:
                leaf_nodes = pageindex_doc.get_all_leaf_nodes()
                sections_data = [
                    {
                        "section_id": node.node_id or "UNKNOWN",
                        "title": node.title,  # 数据库字段名是title
                        "start_page": node.start_index,
                        "end_page": node.end_index
                    }
                    for node in leaf_nodes
                ]
                SectionRepository.batch_create_sections(db, task_id, sections_data)
            
            # 批量保存需求矩阵
            requirements_data = [
                {
                    "matrix_id": req.matrix_id,
                    "requirement": req.requirement,
                    "original_text": req.original_text,
                    "section_id": req.section_id,
                    "section_title": req.section_title,
                    "page_number": req.page_number,
                    "response_suggestion": req.response_suggestion,
                    "risk_warning": req.risk_warning,
                    "notes": req.notes
                }
                for req in final_matrix
            ]
            RequirementRepository.batch_create_requirements(db, task_id, requirements_data)
            
        finally:
            db.close()
        
        # 将树结构转换为字典（用于JSON序列化）
        tree_data = None
        if pageindex_doc:
            tree_data = pageindex_doc.model_dump()
        
        # 更新任务状态为完成
        TaskManager.update_task(
            task_id,
            status="completed",
            progress=100,
            message=f"分析完成！共提取 {len(final_matrix)} 条需求",
            result={
                "requirements_count": len(final_matrix),
                "document_tree": tree_data  # 保存完整树结构
            }
        )
        
    except Exception as e:
        error_msg = f"分析失败: {str(e)}"
        logger.error(error_msg)
        logger.exception(e)
        
        TaskManager.update_task(
            task_id,
            status="failed",
            progress=0,
            message=error_msg
        )


@router.post("/analyze")
async def analyze_tender(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    分析PDF文件
    
    返回task_id，客户端使用task_id订阅SSE进度
    """
    # 验证文件类型
    if not file.filename.lower().endswith('.pdf'):
        return {
            "status": "error",
            "message": "只支持PDF文件"
        }
    
    # 保存上传的文件
    upload_dir = Path("temp/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / file.filename
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    logger.info(f"文件已保存: {file_path}")
    
    # 创建任务
    task_id = TaskManager.create_task(
        pdf_path=str(file_path),
        file_name=file.filename,
        file_size=len(content)
    )
    
    # 启动后台任务
    background_tasks.add_task(
        run_analysis_task,
        task_id=task_id,
        pdf_path=str(file_path)
    )
    
    return {
        "status": "success",
        "task_id": task_id,
        "message": "任务已创建，请使用task_id订阅进度"
    }


@router.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """
    获取分析进度（SSE）
    """
    async def event_generator():
        """生成SSE事件流"""
        last_progress = -1
        retry_count = 0
        max_retries = 600  # 最多等待10分钟
        
        while retry_count < max_retries:
            task = TaskManager.get_task(task_id)
            
            if not task:
                yield f"data: {json.dumps({'error': '任务不存在'}, ensure_ascii=False)}\n\n"
                break
            
            # 只在进度变化时推送
            current_progress = task["progress"]
            if current_progress != last_progress:
                # 转换datetime为字符串以支持JSON序列化
                serializable_task = {
                    **task,
                    "created_at": task["created_at"].isoformat() if isinstance(task.get("created_at"), datetime) else task.get("created_at"),
                    "updated_at": task["updated_at"].isoformat() if isinstance(task.get("updated_at"), datetime) else task.get("updated_at")
                }
                yield f"data: {json.dumps(serializable_task, ensure_ascii=False)}\n\n"
                last_progress = current_progress
            
            # 任务完成或失败，结束流
            if task["status"] in ["completed", "failed"]:
                break
            
            await asyncio.sleep(1)
            retry_count += 1
        
        # 最后发送一个结束标记
        yield f"data: {json.dumps({'status': 'done'}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用Nginx缓冲
        }
    )


@router.get("/task/{task_id}")
async def get_task_info(task_id: str):
    """
    获取任务信息（包括最终需求矩阵）
    """
    task = TaskManager.get_task(task_id)
    
    if not task:
        return {
            "status": "error",
            "message": "任务不存在"
        }
    
    # 如果任务完成，从数据库读取需求矩阵
    if task["status"] == "completed":
        from app.db.repositories import RequirementRepository
        from app.db.database import SessionLocal
        
        db = SessionLocal()
        try:
            requirements = RequirementRepository.get_requirements(db, task_id)
            
            # 转换为字典格式
            matrix = []
            for req in requirements:
                matrix.append({
                    "matrix_id": req.matrix_id,
                    "requirement": req.requirement,
                    "original_text": req.original_text,
                    "section_id": req.section_id,
                    "section_title": req.section_title,
                    "page_number": req.page_number,
                    "response_suggestion": req.response_suggestion,
                    "risk_warning": req.risk_warning,
                    "notes": req.notes
                })
            
            task["matrix"] = matrix
            task["requirements_count"] = len(matrix)
            
            # 如果任务result中包含document_tree，也返回
            if task.get("result") and isinstance(task["result"], dict):
                task["document_tree"] = task["result"].get("document_tree")
        finally:
            db.close()
    
    return task

