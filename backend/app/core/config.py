"""
配置管理模块

使用 pydantic-settings 从环境变量加载配置
支持 .env 文件
"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """应用配置"""
    
    # ==================== LLM统一配置 ====================
    # 支持任何兼容OpenAI接口格式的LLM提供商
    # 包括：OpenAI、DeepSeek、Qwen、Azure OpenAI、本地部署等
    
    llm_api_key: str = Field(
        default="",
        description="LLM API密钥（统一接口）"
    )
    llm_api_base: str = Field(
        default="https://api.openai.com/v1",
        description="LLM API Base URL（统一接口）"
    )
    
    # ==================== 模型配置（按功能角色）====================
    # 每个LangGraph节点可以使用不同的模型
    # 直接填写模型名称即可，如：gpt-4o、deepseek-chat、qwen-plus-latest等
    
    structurizer_model: str = Field(
        default="gpt-4o",
        description="PageIndex文档解析节点使用的模型（结构化提取）"
    )
    
    text_filler_model: str = Field(
        default="gpt-4o-mini",
        description="Text Filler节点使用的模型（原文摘抄）"
    )
    
    summary_model: str = Field(
        default="gpt-4o-mini",
        description="Summary生成使用的模型（摘要生成）"
    )
    
    extractor_model: str = Field(
        default="gpt-4o",
        description="Enricher节点使用的模型（条款提取）"
    )
    
    # 429限流降级备用模型（逗号分隔，按优先级排序）
    # 当主模型被限流时，自动轮换到备用模型
    # 示例：gpt-4o,gpt-4o-mini,gpt-3.5-turbo
    fallback_models: str = Field(
        default="",
        description="429限流时的备用模型列表（逗号分隔），为空则不启用降级"
    )
    
    vision_model: str = Field(
        default="openai:gpt-4o",
        description="视觉模型配置（用于图片/表格的智能分析），格式：provider:model"
    )
    
    # ==================== 应用配置 ====================
    app_env: str = Field(
        default="development",
        description="应用环境：development/production"
    )
    log_level: str = Field(
        default="INFO",
        description="日志级别：DEBUG/INFO/WARNING/ERROR"
    )
    temp_dir: str = Field(
        default="./temp",
        description="临时文件目录"
    )
    
    # ==================== FastAPI配置 ====================
    api_host: str = Field(
        default="0.0.0.0",
        description="API服务器地址"
    )
    api_port: int = Field(
        default=8000,
        description="API服务器端口"
    )
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="允许的CORS来源"
    )
    
    # ==================== Minio配置 ====================
    minio_endpoint: str = Field(
        default="localhost:9000",
        description="MinIO服务器地址（S3 API端口，通常是9000）"
    )
    minio_access_key: str = Field(
        default="minioadmin",
        description="MinIO访问密钥"
    )
    minio_secret_key: str = Field(
        default="minioadmin",
        description="MinIO密钥"
    )
    minio_bucket: str = Field(
        default="document-pdf",
        description="MinIO存储桶名称"
    )
    minio_secure: bool = Field(
        default=False,
        description="是否使用HTTPS连接MinIO"
    )
    
    # ==================== 业务配置 ====================
    max_parallel_workers: int = Field(
        default=5,
        description="最大并行Worker数量（控制LangGraph并发度）"
    )
    confidence_threshold: float = Field(
        default=0.5,
        description="条款提取的最低置信度阈值"
    )
    similarity_threshold: float = Field(
        default=0.85,
        description="去重时的相似度阈值"
    )
    
    # Pydantic v2配置
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# 全局配置实例
settings = Settings()
