"""
异步分析API - 支持SSE进度推送

提供类似RagFlow的实时进度反馈
"""

import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from loguru import logger

from app.api.async_tasks import TaskManager
from app.core.graph import create_tender_analysis_graph
from app.core.states import TenderAnalysisState
from app.core.config import settings

router = APIRouter()


async def run_analysis_task(task_id: str, pdf_path: str, use_mock: bool):
    """
    后台任务：执行分析流程
    
    在执行过程中更新任务状态
    """
    try:
        # 更新状态：开始运行
        TaskManager.update_task(
            task_id,
            status="running",
            progress=0,
            message="开始分析..."
        )
        
        # 阶段1: PDF解析 (0-50%)
        TaskManager.update_task(
            task_id,
            progress=5,
            message="正在解析PDF文档..."
        )
        
        # 创建初始状态
        initial_state = TenderAnalysisState(
            pdf_path=pdf_path,
            use_mock=use_mock,
            task_id=task_id,  # 传入task_id，用于进度更新
            content_list=[],
            markdown="",
            toc=[],
            target_sections=[],
            requirements=[],
            final_matrix=[],
            processing_start_time=None,
            processing_end_time=None,
            error_message=None
        )
        
        TaskManager.update_task(
            task_id,
            progress=10,
            message="正在调用MinerU解析PDF（这可能需要5-10分钟，请耐心等待）..."
        )
        
        # 创建工作流图
        graph = create_tender_analysis_graph()
        
        # 在后台线程中执行（避免阻塞事件循环）
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, graph.invoke, initial_state)
        
        # 阶段2: 需求提取 (60-85%)
        TaskManager.update_task(
            task_id,
            progress=65,
            message="正在分析章节并提取需求条款..."
        )
        
        # 阶段3: 质量检查 (85-100%)
        TaskManager.update_task(
            task_id,
            progress=92,
            message="正在进行质量检查和去重..."
        )
        
        # 完成
        final_matrix = result.get("final_matrix", [])
        target_sections = result.get("target_sections", [])
        
        # 保存章节和需求到数据库
        try:
            from app.db.database import get_db_session
            from app.db.repositories import SectionRepository, RequirementRepository, TaskRepository
            
            db = get_db_session()
            
            # 保存章节
            if target_sections:
                sections_data = [
                    {
                        "section_id": sec.section_id,
                        "title": sec.title,
                        "reason": sec.reason,
                        "priority": sec.priority,
                        "start_page": sec.start_page,
                        "end_page": sec.end_page,
                        "start_index": sec.start_index
                    }
                    for sec in target_sections
                ]
                SectionRepository.batch_create_sections(db, task_id, sections_data)
            
            # 保存需求
            if final_matrix:
                requirements_data = [req.dict() for req in final_matrix]
                RequirementRepository.batch_create_requirements(db, task_id, requirements_data)
            
            # 更新统计信息
            TaskRepository.update_task_stats(
                db,
                task_id=task_id,
                total_sections=len(target_sections),
                total_requirements=len(final_matrix)
            )
            
            db.close()
            logger.info(f"数据库：保存章节和需求完成")
        except Exception as e:
            logger.error(f"保存到数据库失败: {e}")
        
        TaskManager.update_task(
            task_id,
            status="completed",
            progress=100,
            message=f"分析完成！共提取 {len(final_matrix)} 条需求",
            result={
                "requirements_count": len(final_matrix),
                "matrix": [req.dict() for req in final_matrix]
            }
        )
        
        logger.info(f"任务 {task_id} 完成")
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"任务 {task_id} 失败: {e}")
        logger.error(f"详细错误:\n{error_detail}")
        TaskManager.update_task(
            task_id,
            status="failed",
            message=f"分析失败: {str(e)}",
            error=str(e)
        )


@router.post("/analyze/async")
async def analyze_async(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    use_mock: bool = Form(default=False)
):
    """
    异步分析接口
    
    立即返回task_id，客户端通过SSE接口监听进度
    """
    # 保存上传的文件
    import uuid
    from pathlib import Path
    from app.core.config import settings
    
    # 创建临时目录
    temp_dir = Path(settings.temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成唯一文件名并保存
    file_id = uuid.uuid4().hex[:8]
    file_extension = Path(file.filename).suffix if file.filename else ".pdf"
    save_path = temp_dir / f"upload_{file_id}{file_extension}"
    
    # 读取文件内容
    content = await file.read()
    
    # 验证文件不为空
    if not content or len(content) == 0:
        raise ValueError(f"上传的文件为空: {file.filename}")
    
    # 保存文件
    with open(save_path, "wb") as f:
        f.write(content)
    
    # 创建任务（带文件信息）
    task_id = TaskManager.create_task(
        file_name=file.filename or "unknown.pdf",
        file_size=len(content),
        pdf_path=str(save_path),
        use_mock=use_mock
    )
    
    logger.info(f"文件已保存: {save_path} ({len(content)} bytes)")
    
    pdf_path = str(save_path)
    
    # 添加后台任务
    background_tasks.add_task(run_analysis_task, task_id, pdf_path, use_mock)
    
    return {
        "task_id": task_id,
        "message": "任务已创建，请通过SSE接口监听进度",
        "sse_url": f"/analyze/progress/{task_id}"
    }


@router.get("/analyze/progress/{task_id}")
async def stream_progress(task_id: str):
    """
    SSE端点：实时推送任务进度
    
    客户端使用EventSource连接此端点
    
    示例：
    const eventSource = new EventSource('/analyze/progress/task-id');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(data.progress, data.message);
    };
    """
    async def event_generator():
        """生成SSE事件流"""
        try:
            last_progress = -1
            
            while True:
                task = TaskManager.get_task(task_id)
                
                if task is None:
                    yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                    break
                
                # 只在进度变化时发送
                if task["progress"] != last_progress:
                    yield f"data: {json.dumps({
                        'task_id': task_id,
                        'status': task['status'],
                        'progress': task['progress'],
                        'message': task['message'],
                        'result': task.get('result'),
                        'error': task.get('error')
                    })}\n\n"
                    
                    last_progress = task["progress"]
                
                # 任务完成或失败时结束流
                if task["status"] in ["completed", "failed"]:
                    break
                
                # 每秒轮询一次
                await asyncio.sleep(1)
        
        except asyncio.CancelledError:
            logger.info(f"SSE连接断开: {task_id}")
        except Exception as e:
            logger.error(f"SSE错误: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用nginx缓冲
        }
    )


@router.get("/analyze/status/{task_id}")
async def get_task_status(task_id: str):
    """
    获取任务状态（轮询方式）
    
    如果不支持SSE，可以使用此接口轮询
    """
    task = TaskManager.get_task(task_id)
    
    if task is None:
        return {"error": "任务不存在"}
    
    return task

