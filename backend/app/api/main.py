"""
FastAPI入口 - Web API服务

提供文档条款提取的HTTP接口
"""

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from loguru import logger

from app.domain.settings import settings
from app.api.analysis_endpoints import router as analysis_router
from app.api.query_endpoints import router as query_router


# ============================================================================
# FastAPI应用初始化
# ============================================================================

app = FastAPI(
    title="智能文档条款提取API",
    description="基于LangGraph的文档智能分析系统，支持从招标书、合同、合规文档等多种文档中提取结构化条款，支持异步处理和实时进度推送",
    version="0.2.0"
)

# 启动事件：初始化数据库
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    import sys
    
    # 配置loguru日志输出（确保在所有环境下都能看到日志）
    logger.remove()  # 移除默认handler
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG",
        colorize=True
    )
    
    from app.datasources.database import init_db
    init_db()
    logger.info("✅ 数据库初始化完成")

# Analysis endpoints (upload, progress, results, export, delete)
app.include_router(analysis_router, prefix="/api", tags=["Analysis"])

# Query endpoints (tasks, logs, sections, clauses); router already has prefix="/api"
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

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    mineru_available: bool  # 保持字段名兼容性（实际检查PageIndex）
    version: str


# ============================================================================
# 路由端点
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """根路径"""
    return {
        "message": "智能文档条款提取API",
        "version": "0.2.0",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    健康检查端点
    
    检查服务状态和依赖可用性
    """
    # 检查PageIndex是否可用
    pageindex_available = _check_pageindex_available()
    
    return HealthResponse(
        status="ok",
        mineru_available=pageindex_available,  # 保持字段名兼容性
        version="2.0.0"
    )


# ============================================================================
# 辅助函数
# ============================================================================

def _check_pageindex_available() -> bool:
    """检查PageIndex是否可用"""
    try:
        from pageindex import page_index
        return True
    except ImportError:
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
