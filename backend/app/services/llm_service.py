"""
LLM服务封装

封装OpenAI API调用，支持Structured Output
支持多provider动态切换，每个provider使用独立的API配置
"""

from typing import Type, TypeVar, List, Optional, Dict, Union
from pydantic import BaseModel
from openai import OpenAI
from loguru import logger
import base64
from pathlib import Path

from app.core.config import settings


T = TypeVar("T", bound=BaseModel)


class LLMService:
    """
    LLM服务 - 统一OpenAI兼容接口
    
    特性：
    1. 统一的API接口（兼容OpenAI、DeepSeek、Qwen等）
    2. 支持按功能角色配置不同模型
    3. 支持 provider:model 格式（用于vision_model等特殊场景）
    4. 自动429限流降级
    """
    
    def __init__(self):
        # 初始化统一的OpenAI客户端
        if not settings.llm_api_key:
            raise ValueError(
                "必须配置LLM_API_KEY\n"
                "请在.env文件中设置: LLM_API_KEY=your-api-key"
            )
        
        # 统一客户端（所有模型共用）
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_api_base,
            timeout=600.0,
            max_retries=2
        )
        
        # 多provider支持（用于vision_model等特殊场景）
        self._extra_clients: Dict[str, OpenAI] = {}
        
        logger.info(f"LLM服务初始化完成")
        logger.info(f"  - API Base: {settings.llm_api_base}")
        logger.info(f"  - 默认模型: structurizer={settings.structurizer_model}, extractor={settings.extractor_model}")
    
    def _get_client_for_model(self, model: str) -> tuple[OpenAI, str]:
        """
        获取指定模型的client
        
        Args:
            model: 模型名称，支持格式：
                   - "model_name" 如 "gpt-4o" (使用默认client)
                   - "provider:model_name" 如 "qwen:qwen-vl-max-latest" (使用特定provider)
        
        Returns:
            (client, model_name)元组
        """
        # 解析模型字符串
        if ":" in model:
            provider, model_name = model.split(":", 1)
            provider = provider.lower()
            
            # 如果是特殊provider（如qwen用于vision），创建独立client
            if provider != "default":
                if provider not in self._extra_clients:
                    # 暂时使用默认配置（用户需要在vision场景配置独立的API）
                    self._extra_clients[provider] = OpenAI(
                        api_key=settings.llm_api_key,
                        base_url=settings.llm_api_base,
                        timeout=600.0,
                        max_retries=2
                    )
                    logger.debug(f"为provider '{provider}' 创建独立client")
                
                return self._extra_clients[provider], model_name
        else:
            model_name = model
        
        # 使用默认client
        return self._client, model_name
    
    
    def structured_completion(
        self,
        messages: List[dict],
        response_model: Type[T],
        temperature: float = 0.2,
        max_retries: int = 3,
        model: Optional[str] = None
    ) -> T:
        """
        使用Structured Output进行LLM调用
        
        Args:
            messages: 对话消息列表
            response_model: Pydantic模型类（用于结构化输出）
            temperature: 温度参数
            max_retries: 最大重试次数
            model: 可选的模型名称，格式：
                   - "provider:model_name" 如 "deepseek:deepseek-reasoner"
                   - None 使用默认模型
            
        Returns:
            解析后的Pydantic模型实例
        """
        # 获取client和模型名称
        if model:
            client, model_name = self._get_client_for_model(model)
        else:
            # 默认使用structurizer模型
            client, model_name = self._get_client_for_model(settings.structurizer_model)
        
        logger.debug(f"结构化输出调用: model={model_name}")
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"LLM调用开始 (尝试 {attempt + 1}/{max_retries})")
                
                # 尝试使用Structured Output API（如果支持）
                try:
                    response = client.beta.chat.completions.parse(
                        model=model_name,
                        messages=messages,
                        response_format=response_model,
                        temperature=temperature
                    )
                    parsed = response.choices[0].message.parsed
                    
                except Exception as structured_error:
                    # Fallback: 使用JSON mode + 手动解析
                    logger.debug(f"Structured Output API不可用，fallback到JSON mode: {structured_error}")
                    
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
                    
                    response = client.chat.completions.create(
                        model=model_name,
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
        max_tokens: int = 2000,
        model: Optional[str] = None
    ) -> str:
        """
        普通文本生成（不使用Structured Output）
        
        Args:
            messages: 对话消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            model: 可选的模型名称，格式：
                   - "provider:model_name" 如 "deepseek:deepseek-reasoner"
                   - None 使用默认模型
            
        Returns:
            生成的文本
        """
        # 获取client和模型名称
        if model:
            client, model_name = self._get_client_for_model(model)
        else:
            # 默认使用summary模型
            client, model_name = self._get_client_for_model(settings.summary_model)
        
        logger.debug(f"文本生成调用: model={model_name}")
        
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response.choices[0].message.content
            logger.debug(f"LLM文本生成成功，模型: {model_name}，长度: {len(content)}")
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
    
    @staticmethod
    def encode_image_to_base64(image_path: Union[str, Path]) -> str:
        """
        将本地图片编码为base64字符串
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            base64编码的图片字符串（带data URI前缀）
        """
        image_path = Path(image_path)
        
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        # 读取图片并编码
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
            base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # 获取文件扩展名，确定MIME类型
        ext = image_path.suffix.lower()
        mime_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp'
        }
        mime_type = mime_type_map.get(ext, 'image/jpeg')
        
        # 返回data URI格式
        return f"data:{mime_type};base64,{base64_image}"
    
    def vision_completion(
        self,
        text_prompt: str,
        image_inputs: List[Union[str, Path]],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        model: Optional[str] = None
    ) -> str:
        """
        视觉模型调用（支持图片输入）
        
        Args:
            text_prompt: 文本提示词
            image_inputs: 图片输入列表，支持：
                         - 本地文件路径（str或Path）
                         - base64编码的data URI字符串
            temperature: 温度参数
            max_tokens: 最大token数
            model: 可选的模型名称，格式：
                   - "provider:model_name" 如 "qwen:qwen-vl-max-latest"
                   - None 使用vision_model配置
            
        Returns:
            模型生成的文本
        """
        # 解析model参数
        if model:
            if ":" in model:
                model_provider, model_name = model.split(":", 1)
                model_provider = model_provider.lower()
            else:
                # 默认使用qwen provider（视觉模型）
                model_provider = "qwen"
                model_name = model
        else:
            # 使用配置的vision_model
            vision_model_config = settings.vision_model
            if ":" in vision_model_config:
                model_provider, model_name = vision_model_config.split(":", 1)
                model_provider = model_provider.lower()
            else:
                model_provider = "qwen"
                model_name = vision_model_config
        
        logger.debug(f"视觉模型调用: provider={model_provider}, model={model_name}, 图片数量={len(image_inputs)}")
        
        # 构建完整的模型字符串并获取client
        full_model_string = f"{model_provider}:{model_name}"
        try:
            client, actual_model_name = self._get_client_for_model(full_model_string)
        except Exception as e:
            logger.error(f"无法获取视觉模型client: {e}")
            raise
        
        # 构建消息内容（多模态格式）
        content_parts = []
        
        # 添加文本部分
        content_parts.append({
            "type": "text",
            "text": text_prompt
        })
        
        # 添加图片部分
        for image_input in image_inputs:
            # 如果是文件路径，转换为base64
            if isinstance(image_input, (str, Path)):
                image_input_str = str(image_input)
                # 判断是否已经是data URI格式
                if not image_input_str.startswith("data:image"):
                    # 是文件路径，需要编码
                    image_url = self.encode_image_to_base64(image_input)
                else:
                    # 已经是base64 data URI
                    image_url = image_input_str
            else:
                raise ValueError(f"不支持的图片输入类型: {type(image_input)}")
            
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": image_url
                }
            })
        
        # 构建消息
        messages = [
            {
                "role": "user",
                "content": content_parts
            }
        ]
        
        try:
            response = client.chat.completions.create(
                model=actual_model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            content = response.choices[0].message.content
            
            # 输出token使用情况
            if hasattr(response, 'usage'):
                logger.info(
                    f"视觉模型调用成功 - Token使用: "
                    f"输入={response.usage.prompt_tokens}, "
                    f"输出={response.usage.completion_tokens}, "
                    f"总计={response.usage.total_tokens}"
                )
            
            logger.debug(f"视觉模型返回内容长度: {len(content)} 字符")
            return content
            
        except Exception as e:
            logger.error(f"视觉模型调用失败: {e}")
            raise


# 全局LLM服务实例
_llm_service: LLMService = None


def get_llm_service() -> LLMService:
    """
    获取全局LLM服务实例（单例模式）
    """
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
