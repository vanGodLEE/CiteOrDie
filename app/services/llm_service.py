"""
LLM服务封装

封装OpenAI API调用，支持Structured Output
"""

from typing import Type, TypeVar, List, Optional
from pydantic import BaseModel
from openai import OpenAI
from loguru import logger

from app.core.config import settings


T = TypeVar("T", bound=BaseModel)


class LLMService:
    """LLM服务 - 支持多LLM提供商"""
    
    def __init__(self):
        self.provider = settings.llm_provider.lower()
        
        if self.provider == "deepseek":
            # DeepSeek配置
            if not settings.deepseek_api_key:
                raise ValueError(
                    "使用DeepSeek时必须配置DEEPSEEK_API_KEY\n"
                    "请在.env文件中设置: DEEPSEEK_API_KEY=sk-xxx"
                )
            
            self.client = OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_api_base,
                timeout=60.0,  # 60秒超时
                max_retries=2
            )
            self.model = settings.deepseek_model
            logger.info(f"LLM服务初始化完成，使用DeepSeek模型: {self.model}")
        
        elif self.provider == "openai":
            # OpenAI配置
            if not settings.openai_api_key:
                raise ValueError(
                    "使用OpenAI时必须配置OPENAI_API_KEY\n"
                    "请在.env文件中设置: OPENAI_API_KEY=sk-xxx"
                )
            
            self.client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_api_base,
                timeout=60.0,  # 60秒超时
                max_retries=2
            )
            self.model = settings.openai_model
            logger.info(f"LLM服务初始化完成，使用OpenAI模型: {self.model}")
        
        else:
            raise ValueError(
                f"不支持的LLM提供商: {self.provider}。"
                f"支持的选项: openai, deepseek"
            )
    
    def structured_completion(
        self,
        messages: List[dict],
        response_model: Type[T],
        temperature: float = 0.2,
        max_retries: int = 3
    ) -> T:
        """
        使用Structured Output进行LLM调用
        
        Args:
            messages: 对话消息列表
            response_model: Pydantic模型类（用于结构化输出）
            temperature: 温度参数
            max_retries: 最大重试次数
            
        Returns:
            解析后的Pydantic模型实例
        """
        for attempt in range(max_retries):
            try:
                logger.debug(f"LLM调用开始 (尝试 {attempt + 1}/{max_retries})")
                
                if self.provider == "openai":
                    # OpenAI: 使用Structured Output API
                    response = self.client.beta.chat.completions.parse(
                        model=self.model,
                        messages=messages,
                        response_format=response_model,
                        temperature=temperature
                    )
                    parsed = response.choices[0].message.parsed
                    
                else:
                    # DeepSeek/其他: 使用JSON mode + 手动解析
                    # 在system消息中添加JSON schema指示
                    enhanced_messages = messages.copy()
                    
                    # 获取schema
                    schema = response_model.model_json_schema()
                    schema_str = str(schema)
                    
                    # 增强system prompt
                    if enhanced_messages and enhanced_messages[0]["role"] == "system":
                        enhanced_messages[0]["content"] += f"\n\n你必须严格按照以下JSON Schema输出:\n{schema_str}\n\n只输出JSON，不要有任何其他文字。"
                    else:
                        enhanced_messages.insert(0, {
                            "role": "system",
                            "content": f"你必须严格按照以下JSON Schema输出:\n{schema_str}\n\n只输出JSON，不要有任何其他文字。"
                        })
                    
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=enhanced_messages,
                        response_format={"type": "json_object"},
                        temperature=temperature
                    )
                    
                    # 手动解析JSON
                    content = response.choices[0].message.content
                    logger.debug(f"LLM返回内容长度: {len(content)} 字符")
                    logger.debug(f"LLM返回内容预览: {content[:200]}...")
                    
                    import json
                    json_data = json.loads(content)
                    parsed = response_model.model_validate(json_data)
                
                # 输出token使用情况
                if hasattr(response, 'usage'):
                    logger.info(f"LLM调用成功 - Token使用: 输入={response.usage.prompt_tokens}, 输出={response.usage.completion_tokens}, 总计={response.usage.total_tokens}")
                else:
                    logger.debug(f"LLM调用成功，返回类型: {type(parsed).__name__}")
                
                return parsed
                
            except Exception as e:
                logger.warning(f"LLM调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error("LLM调用达到最大重试次数，抛出异常")
                    raise
        
        raise RuntimeError("不应该执行到这里")
    
    def text_completion(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """
        普通文本生成（不使用Structured Output）
        
        Args:
            messages: 对话消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            生成的文本
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response.choices[0].message.content
            logger.debug(f"LLM文本生成成功，长度: {len(content)}")
            return content
            
        except Exception as e:
            logger.error(f"LLM文本生成失败: {e}")
            raise
    
    def create_system_message(self, content: str) -> dict:
        """创建系统消息"""
        return {"role": "system", "content": content}
    
    def create_user_message(self, content: str) -> dict:
        """创建用户消息"""
        return {"role": "user", "content": content}


# 全局LLM服务实例
llm_service = LLMService()
