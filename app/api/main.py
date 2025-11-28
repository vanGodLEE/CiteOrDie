"""
FastAPI入口 - Web API服务

提供招标分析的HTTP接口
"""

import time
import uuid
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger

from app.core.config import settings
from app.core.graph import create_tender_analysis_graph
from app.core.states import TenderAnalysisState, RequirementItem
from app.api.async_analyze import router as async_router
from app.api.query import router as query_router


# ============================================================================
# FastAPI应用初始化
# ============================================================================

app = FastAPI(
    title="智能招标书分析API",
    description="基于LangGraph的招标文件智能分析系统，支持异步处理和实时进度推送",
    version="0.2.0"
)

# 启动事件：初始化数据库
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    from app.db.database import init_db
    init_db()
    logger.info("✅ 数据库初始化完成")

# 注册异步分析路由
app.include_router(async_router, tags=["Async Analysis"])

# 注册查询API路由
app.include_router(query_router, tags=["Query"])

# 配置CORS（允许本地HTML文件访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


# ============================================================================
# 响应模型
# ============================================================================

class AnalysisResponse(BaseModel):
    """分析结果响应"""
    status: str
    requirements_count: int
    matrix: list[RequirementItem]
    processing_time: float
    message: Optional[str] = None



class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    mineru_available: bool
    version: str


# ============================================================================
# 路由端点
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """根路径"""
    return {
        "message": "智能招标书分析API",
        "version": "0.1.0",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    健康检查端点
    
    检查服务状态和依赖可用性
    """
    # 检查MinerU是否可用
    mineru_available = _check_mineru_available()
    
    return HealthResponse(
        status="ok",
        mineru_available=mineru_available,
        version="0.1.0"
    )


@app.post("/analyze", response_model=AnalysisResponse, tags=["Analysis"])
async def analyze_tender(
    file: Optional[UploadFile] = File(None),
    use_mock: bool = Form(default=True)
):
    """
    分析招标文档
    
    Args:
        file: 上传的PDF文件（可选）
        use_mock: 是否使用Mock数据（开发模式）
        
    Returns:
        AnalysisResponse: 包含需求矩阵的分析结果
    """
    start_time = time.time()
    
    try:
        logger.info(f"收到分析请求 (use_mock={use_mock})")
        
        # 处理文件上传（如果不使用Mock）
        pdf_path = ""
        if use_mock:
            pdf_path = "tests/mock_data/sample_tender.json"
        else:
            if not file:
                raise HTTPException(
                    status_code=400,
                    detail="use_mock=False时必须提供PDF文件"
                )
            
            # 保存上传的文件
            pdf_path = await _save_uploaded_file(file)
        
        # 创建初始状态
        initial_state = TenderAnalysisState(
            pdf_path=pdf_path,
            use_mock=use_mock,
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
        
        # 创建并执行工作流
        logger.info("开始执行LangGraph工作流")
        graph = create_tender_analysis_graph()
        result = graph.invoke(initial_state)
        
        # 提取结果
        final_matrix = result.get("final_matrix", [])
        processing_time = time.time() - start_time
        
        logger.info(f"分析完成: {len(final_matrix)} 条需求, 耗时 {processing_time:.2f}秒")
        
        return AnalysisResponse(
            status="success",
            requirements_count=len(final_matrix),
            matrix=final_matrix,
            processing_time=processing_time
        )
        
    except Exception as e:
        logger.error(f"分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================================
# 辅助函数
# ============================================================================

async def _save_uploaded_file(file: UploadFile) -> str:
    """
    保存上传的文件到临时目录
    
    Returns:
        保存的文件路径
    """
    # 创建临时目录
    temp_dir = Path(settings.temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成唯一文件名
    file_id = uuid.uuid4().hex[:8]
    file_extension = Path(file.filename).suffix
    save_path = temp_dir / f"upload_{file_id}{file_extension}"
    
    # 保存文件
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)
    
    logger.info(f"文件已保存到: {save_path}")
    return str(save_path)


def _check_mineru_available() -> bool:
    """检查MinerU是否可用"""
    import subprocess
    try:
        result = subprocess.run(
            [settings.mineru_command, "--version"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# ============================================================================
# 错误处理
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理器"""
    logger.error(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误", "message": str(exc)}
    )
