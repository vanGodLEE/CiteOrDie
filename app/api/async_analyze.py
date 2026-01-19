"""
异步分析API - 支持SSE进度推送
基于PageIndex的PDF文档分析
支持幂等性：相同文件自动复用计算结果
"""

import json
import asyncio
import hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from fastapi import APIRouter, File, UploadFile, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse, Response
from loguru import logger

from app.api.async_tasks import TaskManager
from app.core.graph import create_tender_analysis_graph
from app.core.states import TenderAnalysisState, PageIndexDocument
from app.services.excel_export import ExcelExportService
from urllib.parse import urlparse, urlunparse
MINIO_ENDPOINT = "192.168.100.219:19000"        # 你的 MinIO
PROXY_BASE     = "/tender-minio"
router = APIRouter()

def rewrite_minio_url_for_frontend(u: str) -> str:
    p = urlparse(u)
    if p.netloc != MINIO_ENDPOINT:
        return u  # 非 MinIO 的 URL 不改
    base = urlparse(PROXY_BASE)
    new_path = base.path.rstrip("/") + p.path   # /minio + /bucket/object
    return urlunparse((base.scheme, base.netloc, new_path, "", p.query, ""))

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
            clauses=[],
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
            ClauseRepository
        )
        from app.db.database import SessionLocal
        from app.utils.mineru_coordinate_converter import convert_positions_for_frontend
        
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
            
            # ✅ 转换MinerU坐标为页面坐标（左上原点，单位points，前端直接乘以scale使用）
            # 批量保存条款矩阵
            clauses_data = []
            for clause in final_matrix:
                # 转换positions坐标
                positions = clause.positions if hasattr(clause, 'positions') else []
                if positions:
                    try:
                        positions = convert_positions_for_frontend(positions, pdf_path)
                        logger.debug(f"条款 {clause.matrix_id} 坐标已转换为页面坐标（左上原点，单位points）")
                    except Exception as e:
                        logger.warning(f"转换条款 {clause.matrix_id} 坐标失败: {e}，保留原始坐标")
                
                clauses_data.append({
                    "matrix_id": clause.matrix_id,
                    "type": clause.type,
                    "actor": clause.actor,
                    "action": clause.action,
                    "object": clause.object,
                    "condition": clause.condition,
                    "deadline": clause.deadline,
                    "metric": clause.metric,
                    "original_text": clause.original_text,
                    "section_id": clause.section_id,
                    "section_title": clause.section_title,
                    "page_number": clause.page_number,
                    "image_caption": clause.image_caption if hasattr(clause, 'image_caption') else None,
                    "table_caption": clause.table_caption if hasattr(clause, 'table_caption') else None,
                    "positions": positions  # ✅ 已转换为PDF坐标
                })
            
            ClauseRepository.batch_create_clauses(db, task_id, clauses_data)
            
        finally:
            db.close()
        
        # 将树结构转换为字典（用于JSON序列化和数据库存储）
        tree_data = None
        if pageindex_doc:
            tree_data = pageindex_doc.model_dump()
        
        # ✅ 生成质量报告（不修改原有流程，仅增量添加）
        quality_report = None
        try:
            from app.services.quality_report import QualityReportService
            
            if pageindex_doc and final_matrix:
                logger.info("开始生成质量报告...")
                
                # 将final_matrix转为字典格式
                final_matrix_dict = []
                for clause in final_matrix:
                    if hasattr(clause, 'model_dump'):
                        final_matrix_dict.append(clause.model_dump())
                    elif hasattr(clause, 'dict'):
                        final_matrix_dict.append(clause.dict())
                    else:
                        final_matrix_dict.append(dict(clause))
                
                report = QualityReportService.generate_report(
                    pdf_path=pdf_path,
                    document_tree=tree_data,
                    final_matrix=final_matrix_dict
                )
                
                quality_report = report.model_dump()
                logger.success("✅ 质量报告生成完成")
            else:
                logger.warning("缺少必要数据，跳过质量报告生成")
        except Exception as e:
            logger.error(f"生成质量报告失败（不影响主流程）: {e}")
            logger.exception(e)
        
        # ✅ 转换document_tree中所有节点的positions（移到except外面，确保一定执行）
        def convert_tree_positions(node_data: dict):
            """递归转换树节点的positions"""
            if node_data.get("positions"):
                try:
                    node_data["positions"] = convert_positions_for_frontend(
                        node_data["positions"], 
                        pdf_path
                    )
                except Exception as e:
                    logger.warning(f"转换节点 {node_data.get('title')} 的positions失败: {e}")
            
            # 递归处理子节点
            if node_data.get("nodes"):
                for child in node_data["nodes"]:
                    convert_tree_positions(child)
        
        # 转换根节点和所有子节点
        if tree_data.get("structure"):
            for root_node in tree_data["structure"]:
                convert_tree_positions(root_node)
            
            logger.info("✅ document_tree中所有节点的positions已转换为页面坐标")
        
        # 更新任务状态为完成（包括document_tree和quality_report持久化到数据库）
        TaskManager.update_task(
            task_id,
            status="completed",
            progress=100,
            message=f"分析完成！共提取 {len(final_matrix)} 条条款",
            result={
                "clauses_count": len(final_matrix),
                "document_tree": tree_data,  # 保存完整树结构到内存
                "quality_report": quality_report  # 保存质量报告到内存
            },
            document_tree=tree_data,  # 持久化到数据库
            quality_report=quality_report  # 持久化质量报告到数据库
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


def calculate_file_hash(content: bytes) -> str:
    """
    计算文件的SHA256哈希值
    
    Args:
        content: 文件内容（字节）
        
    Returns:
        64位十六进制哈希字符串
    """
    sha256_hash = hashlib.sha256()
    sha256_hash.update(content)
    return sha256_hash.hexdigest()


@router.post("/analyze")
async def analyze_tender(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    """
    分析PDF文件（支持幂等性）
    
    幂等性策略：
    1. 计算上传文件的SHA256哈希值
    2. 检查数据库中是否存在相同哈希的已完成任务
    3. 如果存在，直接返回已有任务的task_id（reused=true）
    4. 如果不存在，创建新任务并开始分析（reused=false）
    
    返回：
        - task_id: 任务ID
        - reused: 是否复用已有结果
        - message: 提示信息
    """
    # 验证文件类型
    if not file.filename.lower().endswith('.pdf'):
        return {
            "status": "error",
            "message": "只支持PDF文件"
        }
    
    # 读取文件内容
    content = await file.read()
    file_size = len(content)
    
    # ✅ 计算文件哈希
    file_hash = calculate_file_hash(content)
    logger.info(f"文件哈希: {file_hash[:16]}... (完整: {file_hash})")
    
    # ✅ 检查是否已存在相同文件的任务（幂等性检查）
    from app.db.repositories import TaskRepository
    from app.db.database import SessionLocal
    
    db = SessionLocal()
    try:
        existing_task = TaskRepository.find_by_file_hash(db, file_hash)
        
        if existing_task and existing_task.status == "completed":
            # 找到已完成的任务，直接复用
            logger.success(f"✅ 复用已有任务: {existing_task.task_id} (文件: {existing_task.file_name})")
            logger.info(f"   - 完成时间: {existing_task.completed_at}")
            logger.info(f"   - 条款数: {existing_task.total_clauses}")
            logger.info(f"   - 耗时: {existing_task.elapsed_seconds:.1f}秒")
            
            # 将任务加载到内存（如果还没有）
            if not TaskManager.get_task(existing_task.task_id):
                TaskManager.load_completed_task(existing_task.task_id)
            
            return {
                "status": "success",
                "task_id": existing_task.task_id,
                "reused": True,
                "message": f"检测到相同文件，复用已有分析结果（完成于 {existing_task.completed_at.strftime('%Y-%m-%d %H:%M:%S')}）"
            }
        
        elif existing_task and existing_task.status == "running":
            # 任务正在运行中
            logger.info(f"⏳ 任务正在运行: {existing_task.task_id}")
            return {
                "status": "success",
                "task_id": existing_task.task_id,
                "reused": True,
                "message": "检测到相同文件正在分析中，请等待完成"
            }
        
        else:
            # 没有找到可复用的任务，或之前的任务失败了
            if existing_task:
                logger.info(f"⚠️  历史任务状态为 {existing_task.status}，创建新任务")
            else:
                logger.info("🆕 首次上传此文件，创建新任务")
    
    finally:
        db.close()
    
    # 保存上传的文件
    upload_dir = Path("temp/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / file.filename
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    logger.info(f"文件已保存: {file_path}")
    
    # 创建新任务
    task_id = TaskManager.create_task(
        pdf_path=str(file_path),
        file_name=file.filename,
        file_size=file_size,
        file_hash=file_hash  # ✅ 传递文件哈希
    )
    
    # 上传到MinIO
    try:
        from app.services.minio_service import get_minio_service
        minio_service = get_minio_service()
        minio_url = minio_service.upload_pdf(str(file_path), task_id)
        
        # 更新任务的minio_url
        from app.db.repositories import TaskRepository
        from app.db.database import SessionLocal
        db = SessionLocal()
        try:
            TaskRepository.update_task(db, task_id, {"minio_url": minio_url})
        finally:
            db.close()
            
        logger.info(f"✓ PDF已上传到MinIO: {minio_url}")
    except Exception as e:
        logger.warning(f"上传到MinIO失败（不影响分析流程）: {e}")
    
    # 启动后台任务
    background_tasks.add_task(
        run_analysis_task,
        task_id=task_id,
        pdf_path=str(file_path)
    )
    
    return {
        "status": "success",
        "task_id": task_id,
        "reused": False,
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
                    "updated_at": task["updated_at"].isoformat() if isinstance(task.get("updated_at"), datetime) else task.get("updated_at"),
                    "start_time": task["start_time"].isoformat() if task.get("start_time") and isinstance(task.get("start_time"), datetime) else None,
                    "elapsed_seconds": task.get("elapsed_seconds", 0),
                    "logs": task.get("logs", [])
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
    获取任务信息（包括最终条款矩阵和文档树）
    
    重要：无论任务是从内存还是数据库恢复，都能正确返回完整数据
    
    ✅ positions已转换为页面坐标（左上角原点，单位points），前端需乘以scale后使用
    具体使用方法：
    1. 计算scale: scale = containerWidth / viewport.width
    2. 应用scale到坐标: vx = x * scale, vy = y * scale
    3. 绘制高亮: ctx.strokeRect(vx0, vy0, vx1-vx0, vy1-vy0)
    """
    task = TaskManager.get_task(task_id)
    
    if not task:
        return {
            "status": "error",
            "message": "任务不存在"
        }
    
    # 如果任务完成，从数据库读取完整数据（支持重启后恢复）
    if task["status"] == "completed":
        from app.db.repositories import ClauseRepository, TaskRepository
        from app.db.database import SessionLocal
        import json
        
        db = SessionLocal()
        try:
            # 1. 读取条款矩阵（✅ 包含已转换的PDF坐标）
            clauses_data = ClauseRepository.get_clauses_with_positions(db, task_id)
            task_record = TaskRepository.get_task(db, task_id)
            
            # positions已在保存时转换为PDF坐标，直接使用
            matrix = []
            for clause in clauses_data:
                matrix.append({
                    "matrix_id": clause["matrix_id"],
                    "type": clause["type"],
                    "actor": clause.get("actor"),
                    "action": clause.get("action"),
                    "object": clause.get("object"),
                    "condition": clause.get("condition"),
                    "deadline": clause.get("deadline"),
                    "metric": clause.get("metric"),
                    "original_text": clause["original_text"],
                    "section_id": clause["section_id"],
                    "section_title": clause["section_title"],
                    "page_number": clause["page_number"],
                    "image_caption": clause.get("image_caption"),
                    "table_caption": clause.get("table_caption"),
                    "positions": clause.get("positions", [])  # ✅ 已转换为PDF坐标
                })
            
            # 总是设置matrix和clauses_count
            task["matrix"] = matrix
            task["clauses_count"] = len(matrix)
            
            # 2. 读取document_tree（优先从内存，再从数据库）
            document_tree = None
            
            # 尝试从内存result获取
            if task.get("result") and isinstance(task["result"], dict):
                document_tree = task["result"].get("document_tree")
            
            # 如果内存没有，从数据库读取
            if not document_tree:
                if task_record and task_record.document_tree_json:
                    try:
                        document_tree = json.loads(task_record.document_tree_json)
                    except Exception as e:
                        logger.error(f"解析document_tree失败: {e}")
            
            # ✅ document_tree中的positions已在保存时转换（左上原点，单位points）
            task["document_tree"] = document_tree
            
            # 3. 读取quality_report（优先从内存，再从数据库）
            quality_report = None
            
            # 尝试从内存result获取
            if task.get("result") and isinstance(task["result"], dict):
                quality_report = task["result"].get("quality_report")
            
            # 如果内存没有，从数据库读取
            if not quality_report:
                if task_record and task_record.quality_report_json:
                    try:
                        quality_report = json.loads(task_record.quality_report_json)
                    except Exception as e:
                        logger.error(f"解析quality_report失败: {e}")
            
            task["quality_report"] = quality_report
            
            logger.info(f"任务 {task_id}: 返回 {len(matrix)} 条条款")
            if quality_report:
                logger.info(f"  - 包含质量报告: 解析置信度={quality_report.get('avg_parse_confidence', 0):.2%}")
                
        finally:
            db.close()
    
    return task


# ✅ 坐标转换已在保存时完成：
#    - 条款的positions：MinerU归一化坐标(0-1000) → 页面坐标(左上原点，单位points）
#    - 节点的positions：MinerU归一化坐标(0-1000) → 页面坐标(左上原点，单位points)
# 前端Canvas可直接使用，只需应用scale：vx = x * scale, vy = y * scale


@router.get("/download/excel/{task_id}")
async def download_excel(task_id: str):
    """
    下载Excel格式的条款矩阵
    
    Args:
        task_id: 任务ID
        
    Returns:
        Excel文件下载
    """
    # 获取任务信息
    task = TaskManager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    # 获取document_tree
    document_tree = None
    if task.get("result") and isinstance(task["result"], dict):
        document_tree = task["result"].get("document_tree")
    
    if not document_tree:
        raise HTTPException(status_code=404, detail="未找到文档结构数据")
    
    try:
        # 转换为PageIndexDocument对象
        doc = PageIndexDocument(**document_tree)
        
        # 生成Excel
        excel_bytes = ExcelExportService.export_to_excel(doc)
        
        # 生成文件名
        file_name = ExcelExportService.get_filename(doc.doc_name)
        
        # URL编码文件名（支持中文）
        # 使用 RFC 2231 标准格式
        encoded_filename = quote(file_name.encode('utf-8'))
        
        # 返回文件
        return Response(
            content=excel_bytes.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                # 同时提供ASCII后备和UTF-8编码的文件名，确保最大兼容性
                "Content-Disposition": f"attachment; filename=\"clause_matrix.xlsx\"; filename*=UTF-8''{encoded_filename}"
            }
        )
    except Exception as e:
        logger.error(f"生成Excel失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成Excel失败: {str(e)}")


@router.get("/quality-report/{task_id}")
async def get_quality_report(task_id: str):
    """
    获取任务的质量报告
    
    Args:
        task_id: 任务ID
        
    Returns:
        包含4个质量指标的报告
    """
    # 获取任务信息
    task = TaskManager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")
    
    # 从数据库获取quality_report
    from app.db.repositories import TaskRepository
    from app.db.database import SessionLocal
    import json
    
    db = SessionLocal()
    try:
        task_record = TaskRepository.get_task(db, task_id)
        if not task_record:
            raise HTTPException(status_code=404, detail="任务记录不存在")
        
        quality_report = None
        
        # 1. 尝试从内存获取
        if task.get("result") and isinstance(task["result"], dict):
            quality_report = task["result"].get("quality_report")
        
        # 2. 如果内存没有，从数据库读取
        if not quality_report and task_record.quality_report_json:
            try:
                quality_report = json.loads(task_record.quality_report_json)
            except Exception as e:
                logger.error(f"解析quality_report失败: {e}")
        
        if not quality_report:
            raise HTTPException(status_code=404, detail="未找到质量报告（可能是历史任务，请重新分析）")
        
        return {
            "status": "success",
            "task_id": task_id,
            "file_name": task_record.file_name,
            "quality_report": quality_report
        }
        
    finally:
        db.close()


@router.delete("/task/{task_id}")
async def delete_task(task_id: str):
    """
    删除任务及其所有相关文件
    
    删除内容包括：
    1. 数据库记录（task, logs, sections, clauses）
    2. MinIO中的PDF文件
    3. 本地PDF文件（temp/uploads）
    4. MinerU输出目录
    5. 日志文件
    6. middle_json文件
    
    Args:
        task_id: 任务ID
        
    Returns:
        删除结果
    """
    from app.db.repositories import TaskRepository
    from app.db.database import SessionLocal
    from app.services.task_cleanup import TaskCleanupService
    
    db = SessionLocal()
    try:
        # 1. 获取任务信息（用于清理文件）
        task_record = TaskRepository.get_task(db, task_id)
        if not task_record:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        pdf_path = task_record.pdf_path
        file_name = task_record.file_name
        
        logger.info(f"开始删除任务: {task_id} ({file_name})")
        
        # 2. 清理所有相关文件
        cleanup_results = TaskCleanupService.cleanup_task(
            task_id=task_id,
            pdf_path=pdf_path,
            file_name=file_name
        )
        
        # 3. 删除数据库记录（包括级联删除logs/sections/clauses）
        db_deleted = TaskRepository.delete_task(db, task_id)
        cleanup_results["database"] = db_deleted
        
        # 4. 从内存中清除任务缓存
        TaskManager.delete_task(task_id)
        
        # 统计成功项
        success_items = [k for k, v in cleanup_results.items() if v and k != "task_id"]
        total_items = len(cleanup_results) - 1  # 减去task_id字段
        
        logger.success(f"✅ 任务删除完成: {task_id}，成功 {len(success_items)}/{total_items} 项")
        
        return {
            "status": "success",
            "task_id": task_id,
            "message": f"任务已删除（{len(success_items)}/{total_items}项成功）",
            "details": cleanup_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除任务失败: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")
    finally:
        db.close()


@router.get("/pdf/{task_id}")
async def get_pdf_url(task_id: str):
    """
    获取PDF文件的MinIO访问URL
    
    Args:
        task_id: 任务ID
        
    Returns:
        包含PDF URL的响应
    """
    # 获取任务信息
    task = TaskManager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 从数据库获取minio_url
    from app.db.repositories import TaskRepository
    from app.db.database import SessionLocal
    
    db = SessionLocal()
    try:
        task_record = TaskRepository.get_task(db, task_id)
        if not task_record:
            raise HTTPException(status_code=404, detail="任务记录不存在")
        
        # 每次都从MinIO动态生成预签名URL（不从数据库读取）
        # 原因：预签名URL有24小时有效期，不适合长期存储
        try:
            from app.services.minio_service import get_minio_service
            minio_service = get_minio_service()
            # ✅ 修复：正确解包元组返回值
            direct_url, proxy_url = minio_service.get_pdf_url(task_id)
            
            if not direct_url:
                raise HTTPException(status_code=404, detail="未找到PDF文件")
            
            logger.debug(f"生成预签名URL成功 (直接): {direct_url[:100]}...")
            logger.debug(f"生成预签名URL成功 (代理): {proxy_url[:100]}...")
            
            return {
                "status": "success",
                "task_id": task_id,
                "file_name": task_record.file_name,
                "minio_url": direct_url,  # 直接访问URL（内网）
                "proxy_url": proxy_url,    # Nginx代理URL（前端使用）
                "message": "PDF文件URL获取成功（24小时有效）"
            }
            
        except Exception as e:
            logger.error(f"从MinIO生成预签名URL失败: {e}")
            raise HTTPException(status_code=500, detail=f"生成访问URL失败: {str(e)}")
        
    finally:
        db.close()

