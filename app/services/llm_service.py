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
    LLM服务 - 支持多LLM提供商动态切换
    
    特性：
    1. 支持多provider（openai, deepseek等）
    2. 每个provider使用独立的API配置
    3. Client缓存机制，避免重复创建
    4. 支持 provider:model 格式动态选择
    """
    
    def __init__(self):
        self.default_provider = settings.llm_provider.lower()
        self.default_model = None
        
        # Client缓存：{provider: OpenAI客户端}
        self._clients: Dict[str, OpenAI] = {}
        
        # 初始化默认provider的client
        self._init_default_client()
        
        logger.info(f"LLM服务初始化完成")
        logger.info(f"  - 默认Provider: {self.default_provider}")
        logger.info(f"  - 默认Model: {self.default_model}")
    
    def _init_default_client(self):
        """初始化默认provider的client"""
        if self.default_provider == "deepseek":
            if not settings.deepseek_api_key:
                raise ValueError(
                    "使用DeepSeek时必须配置DEEPSEEK_API_KEY\n"
                    "请在.env文件中设置: DEEPSEEK_API_KEY=sk-xxx"
                )
            
            self._clients["deepseek"] = OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_api_base,
                timeout=600.0,
                max_retries=2
            )
            self.default_model = settings.deepseek_model
            logger.debug(f"DeepSeek client已初始化: {settings.deepseek_api_base}")
        
        elif self.default_provider == "openai":
            if not settings.openai_api_key:
                raise ValueError(
                    "使用OpenAI时必须配置OPENAI_API_KEY\n"
                    "请在.env文件中设置: OPENAI_API_KEY=sk-xxx"
                )
            
            self._clients["openai"] = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_api_base,
                timeout=600.0,
                max_retries=2
            )
            self.default_model = settings.openai_model
            logger.debug(f"OpenAI client已初始化: {settings.openai_api_base}")
        
        elif self.default_provider == "qwen":
            if not settings.qwen_api_key:
                raise ValueError(
                    "使用Qwen时必须配置QWEN_API_KEY\n"
                    "请在.env文件中设置: QWEN_API_KEY=sk-xxx"
                )
            
            self._clients["qwen"] = OpenAI(
                api_key=settings.qwen_api_key,
                base_url=settings.qwen_api_base,
                timeout=600.0,
                max_retries=2
            )
            self.default_model = settings.qwen_vl_model
            logger.debug(f"Qwen client已初始化: {settings.qwen_api_base}")
        
        else:
            raise ValueError(
                f"不支持的LLM提供商: {self.default_provider}。"
                f"支持的选项: openai, deepseek, qwen"
            )
    
    def _get_client(self, provider: str) -> OpenAI:
        """
        获取指定provider的client，支持动态创建和缓存
        
        Args:
            provider: provider名称（openai, deepseek等）
            
        Returns:
            OpenAI客户端
        """
        provider = provider.lower()
        
        # 如果已缓存，直接返回
        if provider in self._clients:
            return self._clients[provider]
        
        # 动态创建新的client
        if provider == "deepseek":
            if not settings.deepseek_api_key:
                raise ValueError(
                    f"尝试使用provider '{provider}' 但未配置DEEPSEEK_API_KEY"
                )
            
            client = OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_api_base,
                timeout=600.0,
                max_retries=2
            )
            self._clients[provider] = client
            logger.debug(f"动态创建DeepSeek client: {settings.deepseek_api_base}")
            return client
        
        elif provider == "openai":
            if not settings.openai_api_key:
                raise ValueError(
                    f"尝试使用provider '{provider}' 但未配置OPENAI_API_KEY"
                )
            
            client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_api_base,
                timeout=600.0,
                max_retries=2
            )
            self._clients[provider] = client
            logger.debug(f"动态创建OpenAI client: {settings.openai_api_base}")
            return client
        
        elif provider == "qwen":
            if not settings.qwen_api_key:
                raise ValueError(
                    f"尝试使用provider '{provider}' 但未配置QWEN_API_KEY"
                )
            
            client = OpenAI(
                api_key=settings.qwen_api_key,
                base_url=settings.qwen_api_base,
                timeout=600.0,
                max_retries=2
            )
            self._clients[provider] = client
            logger.debug(f"动态创建Qwen client: {settings.qwen_api_base}")
            return client
        
        else:
            raise ValueError(
                f"不支持的provider: {provider}。"
                f"支持的选项: openai, deepseek, qwen"
            )
    
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
        # 解析model参数
        if model:
            if ":" in model:
                model_provider, model_name = model.split(":", 1)
                model_provider = model_provider.lower()
            else:
                # 使用默认provider
                model_provider = self.default_provider
                model_name = model
        else:
            # 使用默认配置
            model_provider = self.default_provider
            model_name = self.default_model
        
        logger.debug(f"结构化输出调用: provider={model_provider}, model={model_name}")
        
        # 获取对应provider的client
        try:
            client = self._get_client(model_provider)
        except ValueError as e:
            logger.error(f"无法获取provider '{model_provider}' 的client: {e}")
            raise
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"LLM调用开始 (尝试 {attempt + 1}/{max_retries})")
                
                if model_provider == "openai":
                    # OpenAI: 使用Structured Output API
                    response = client.beta.chat.completions.parse(
                        model=model_name,
                        messages=messages,
                        response_format=response_model,
                        temperature=temperature
                    )
                    parsed = response.choices[0].message.parsed
                    
                else:
                    # DeepSeek/其他: 使用JSON mode + 手动解析
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
        # 解析model参数
        if model:
            if ":" in model:
                model_provider, model_name = model.split(":", 1)
                model_provider = model_provider.lower()
            else:
                model_provider = self.default_provider
                model_name = model
        else:
            model_provider = self.default_provider
            model_name = self.default_model
        
        logger.debug(f"文本生成调用: provider={model_provider}, model={model_name}")
        
        # 获取对应provider的client
        try:
            client = self._get_client(model_provider)
        except ValueError as e:
            logger.error(f"无法获取provider '{model_provider}' 的client: {e}")
            raise
        
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
        
        # 获取对应provider的client
        try:
            client = self._get_client(model_provider)
        except ValueError as e:
            logger.error(f"无法获取provider '{model_provider}' 的client: {e}")
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
                model=model_name,
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
