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
    
    # ==================== LLM配置 ====================
    llm_provider: str = Field(
        default="openai",
        description="LLM提供商：openai / deepseek / azure"
    )
    
    # OpenAI配置
    openai_api_key: str = Field(default="", description="OpenAI API密钥")
    openai_api_base: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI API基础URL"
    )
    openai_model: str = Field(
        default="gpt-4o-2024-08-06",
        description="OpenAI模型名称（必须支持Structured Output）"
    )
    
    # DeepSeek配置
    deepseek_api_key: str = Field(
        default="",
        description="DeepSeek API密钥"
    )
    deepseek_api_base: str = Field(
        default="https://api.deepseek.com/v1",
        description="DeepSeek API基础URL"
    )
    deepseek_model: str = Field(
        default="deepseek-chat",
        description="DeepSeek模型名称"
    )
    
    # Qwen-VL配置（阿里云通义千问视觉模型）
    qwen_api_key: str = Field(
        default="",
        description="Qwen API密钥（用于视觉模型）"
    )
    qwen_api_base: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="Qwen API基础URL"
    )
    qwen_vl_model: str = Field(
        default="qwen-vl-max-latest",
        description="Qwen视觉模型名称"
    )
    
    # ==================== 节点级LLM配置 ====================
    # 每个LangGraph节点可以使用不同的模型
    # 支持格式：
    # - "provider:model" 如 "deepseek:deepseek-chat" 或 "openai:gpt-4o"
    # - "model" 如 "deepseek-chat"（使用默认provider）
    
    structurizer_model: str = Field(
        default="deepseek:deepseek-chat",
        description="PageIndex文档解析节点使用的模型（结构化提取）"
    )
    
    # 429限流降级备用模型（逗号分隔）
    # 当主模型被限流时，自动轮换到备用模型
    # 示例：qwen3-max-preview,qwen-max,qwen-max
    fallback_models: str = Field(
        default="",
        description="429限流时的备用模型列表（逗号分隔），为空则不启用降级"
    )
    
    text_filler_model: str = Field(
        default="deepseek:deepseek-chat",
        description="Text Filler节点使用的模型（原文摘抄）"
    )
    
    summary_model: str = Field(
        default="deepseek:deepseek-chat",
        description="Summary生成使用的模型（摘要生成）"
    )
    
    extractor_model: str = Field(
        default="deepseek:deepseek-chat",
        description="Enricher节点使用的模型（条款提取）"
    )
    
    auditor_model: str = Field(
        default="deepseek:deepseek-chat",
        description="Auditor节点使用的模型（目前未使用LLM）"
    )
    
    vision_model: str = Field(
        default="qwen:qwen-vl-max-latest",
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
        default="192.168.100.219:19000",
        description="MinIO服务器地址（S3 API端口，通常是9000或19000）"
    )
    minio_access_key: str = Field(
        default="rag_flow",
        description="MinIO访问密钥"
    )
    minio_secret_key: str = Field(
        default="infini_rag_flow",
        description="MinIO密钥"
    )
    minio_bucket: str = Field(
        default="tender-pdf",
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
