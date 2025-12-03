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
    
    # ==================== 节点级LLM配置 ====================
    # 每个LangGraph节点可以使用不同的模型
    
    structurizer_model: str = Field(
        default="deepseek-chat",
        description="PageIndex解析使用的模型"
    )
    
    extractor_model: str = Field(
        default="deepseek-chat",
        description="Extractor节点使用的模型"
    )
    
    auditor_model: str = Field(
        default="deepseek-chat",
        description="Auditor节点使用的模型"
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
    
    # ==================== 业务配置 ====================
    max_parallel_workers: int = Field(
        default=5,
        description="最大并行Worker数量（控制LangGraph并发度）"
    )
    confidence_threshold: float = Field(
        default=0.5,
        description="需求提取的最低置信度阈值"
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
