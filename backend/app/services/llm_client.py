"""
LLM client wrapper for OpenAI-compatible APIs.

Provides three calling modes:
* **structured_completion** – returns a validated Pydantic model instance.
* **text_completion** – returns free-form text.
* **vision_completion** – accepts images and returns text.

Supports a ``provider:model`` syntax so that different API endpoints can
be used for different model roles (e.g. a vision provider).
"""

import base64
import json
from pathlib import Path
from typing import Dict, List, Optional, Type, TypeVar, Union

from loguru import logger
from openai import OpenAI
from pydantic import BaseModel

from app.domain.settings import settings

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """
    Unified LLM client (OpenAI-compatible).

    Features:
    1. Single API interface compatible with OpenAI / DeepSeek / Qwen / etc.
    2. Per-role model configuration (structurizer, extractor, summary, vision).
    3. ``provider:model`` notation for routing to different endpoints.
    4. Automatic retry with fallback from Structured Output to JSON-mode.
    """

    def __init__(self) -> None:
        if not settings.llm_api_key:
            raise ValueError(
                "LLM_API_KEY is required.\n"
                "Set it in the .env file: LLM_API_KEY=your-api-key"
            )

        # Default client shared by all models
        self._client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_api_base,
            timeout=600.0,
            max_retries=2,
        )

        # Extra clients keyed by provider name (e.g. "qwen" for vision)
        self._extra_clients: Dict[str, OpenAI] = {}

        logger.info("LLM client initialised")
        logger.info(f"  API base: {settings.llm_api_base}")
        logger.info(
            f"  Default models: structurizer={settings.structurizer_llm_name}, "
            f"extractor={settings.extractor_llm_name}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client_for_model(self, model: str) -> tuple[OpenAI, str]:
        """
        Resolve a model string into an ``(OpenAI_client, model_name)`` pair.

        Args:
            model: Either ``"model_name"`` (uses default client) or
                   ``"provider:model_name"`` (creates / reuses a
                   provider-specific client).

        Returns:
            Tuple of ``(client, model_name)``.
        """
        if ":" in model:
            provider, model_name = model.split(":", 1)
            provider = provider.lower()

            if provider != "default":
                if provider not in self._extra_clients:
                    self._extra_clients[provider] = OpenAI(
                        api_key=settings.llm_api_key,
                        base_url=settings.llm_api_base,
                        timeout=600.0,
                        max_retries=2,
                    )
                    logger.debug(f"Created extra client for provider '{provider}'")

                return self._extra_clients[provider], model_name
        else:
            model_name = model

        return self._client, model_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def structured_completion(
        self,
        messages: List[dict],
        response_model: Type[T],
        temperature: float = 0.2,
        max_retries: int = 3,
        model: Optional[str] = None,
    ) -> T:
        """
        Call an LLM and return a validated Pydantic model instance.

        Tries the Structured Output API first; falls back to JSON-mode
        with manual parsing if the provider does not support it.

        Args:
            messages: Chat messages.
            response_model: Target Pydantic class for structured output.
            temperature: Sampling temperature.
            max_retries: Maximum number of attempts.
            model: Optional ``"provider:model_name"``; defaults to
                   ``settings.structurizer_llm_name``.

        Returns:
            Validated *response_model* instance.
        """
        if model:
            client, model_name = self._get_client_for_model(model)
        else:
            client, model_name = self._get_client_for_model(settings.structurizer_llm_name)

        logger.debug(f"Structured completion: model={model_name}")

        for attempt in range(max_retries):
            try:
                logger.debug(f"LLM call attempt {attempt + 1}/{max_retries}")

                # Try Structured Output API
                try:
                    response = client.beta.chat.completions.parse(
                        model=model_name,
                        messages=messages,
                        response_format=response_model,
                        temperature=temperature,
                    )
                    parsed = response.choices[0].message.parsed

                except Exception as structured_error:
                    # Fallback: JSON-mode + manual parsing
                    logger.debug(
                        f"Structured Output API unavailable, falling back to "
                        f"JSON-mode: {structured_error}"
                    )

                    enhanced_messages = messages.copy()
                    schema_str = str(response_model.model_json_schema())

                    # NOTE: The Chinese prompt text is intentional – changing
                    # the language may alter LLM output quality.
                    if enhanced_messages and enhanced_messages[0]["role"] == "system":
                        enhanced_messages[0]["content"] += (
                            f"\n\n你必须严格按照以下JSON Schema输出:\n{schema_str}"
                            "\n\n只输出JSON，不要有任何其他文字。"
                        )
                    else:
                        enhanced_messages.insert(0, {
                            "role": "system",
                            "content": (
                                f"你必须严格按照以下JSON Schema输出:\n{schema_str}"
                                "\n\n只输出JSON，不要有任何其他文字。"
                            ),
                        })

                    response = client.chat.completions.create(
                        model=model_name,
                        messages=enhanced_messages,
                        response_format={"type": "json_object"},
                        temperature=temperature,
                    )

                    content = response.choices[0].message.content
                    logger.debug(f"LLM response length: {len(content)} chars")
                    logger.debug(f"LLM response preview: {content[:200]}...")

                    json_data = json.loads(content)
                    parsed = response_model.model_validate(json_data)

                # Log token usage
                if hasattr(response, "usage") and response.usage:
                    logger.info(
                        f"LLM call succeeded – tokens: "
                        f"prompt={response.usage.prompt_tokens}, "
                        f"completion={response.usage.completion_tokens}, "
                        f"total={response.usage.total_tokens}"
                    )
                else:
                    logger.debug(f"LLM call succeeded, result type: {type(parsed).__name__}")

                return parsed

            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error("LLM call exhausted all retries")
                    raise

        raise RuntimeError("Unreachable: all retries exhausted")

    def text_completion(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> str:
        """
        Generate free-form text.

        Args:
            messages: Chat messages.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            model: Optional ``"provider:model_name"``; defaults to
                   ``settings.summarizer_llm_name``.

        Returns:
            Generated text string.
        """
        if model:
            client, model_name = self._get_client_for_model(model)
        else:
            client, model_name = self._get_client_for_model(settings.summarizer_llm_name)

        logger.debug(f"Text completion: model={model_name}")

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            content = response.choices[0].message.content
            logger.debug(f"Text completion succeeded, model={model_name}, length={len(content)}")
            return content

        except Exception as e:
            logger.error(f"Text completion failed: {e}")
            raise

    # ------------------------------------------------------------------
    # Message helpers
    # ------------------------------------------------------------------

    @staticmethod
    def create_system_message(content: str) -> dict:
        """Build a system-role message dict."""
        return {"role": "system", "content": content}

    @staticmethod
    def create_user_message(content: str) -> dict:
        """Build a user-role message dict."""
        return {"role": "user", "content": content}

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------

    @staticmethod
    def encode_image_to_base64(image_path: Union[str, Path]) -> str:
        """
        Encode a local image file as a ``data:`` URI with base64 payload.

        Args:
            image_path: Path to the image file.

        Returns:
            Data URI string (e.g. ``data:image/png;base64,…``).

        Raises:
            FileNotFoundError: If *image_path* does not exist.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        with open(image_path, "rb") as fh:
            base64_image = base64.b64encode(fh.read()).decode("utf-8")

        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
        }
        mime_type = mime_map.get(image_path.suffix.lower(), "image/jpeg")
        return f"data:{mime_type};base64,{base64_image}"

    def vision_completion(
        self,
        text_prompt: str,
        image_inputs: List[Union[str, Path]],
        temperature: float = 0.3,
        max_tokens: int = 2000,
        model: Optional[str] = None,
    ) -> str:
        """
        Call a vision-capable model with text and images.

        Args:
            text_prompt: Text prompt.
            image_inputs: List of image sources – local file paths or
                          ``data:image/…`` URIs.
            temperature: Sampling temperature.
            max_tokens: Maximum output tokens.
            model: Optional ``"provider:model_name"``; defaults to
                   ``settings.img_handler_model``.

        Returns:
            Generated text string.
        """
        # Resolve provider and model name
        if model:
            if ":" in model:
                model_provider, model_name = model.split(":", 1)
                model_provider = model_provider.lower()
            else:
                model_provider = "qwen"
                model_name = model
        else:
            vision_cfg = settings.img_handler_model
            if ":" in vision_cfg:
                model_provider, model_name = vision_cfg.split(":", 1)
                model_provider = model_provider.lower()
            else:
                model_provider = "qwen"
                model_name = vision_cfg

        logger.debug(
            f"Vision completion: provider={model_provider}, "
            f"model={model_name}, images={len(image_inputs)}"
        )

        full_model_string = f"{model_provider}:{model_name}"
        try:
            client, actual_model_name = self._get_client_for_model(full_model_string)
        except Exception as e:
            logger.error(f"Failed to obtain vision-model client: {e}")
            raise

        # Build multimodal message
        content_parts: list[dict] = [{"type": "text", "text": text_prompt}]

        for img in image_inputs:
            if isinstance(img, (str, Path)):
                img_str = str(img)
                if not img_str.startswith("data:image"):
                    image_url = self.encode_image_to_base64(img)
                else:
                    image_url = img_str
            else:
                raise ValueError(f"Unsupported image input type: {type(img)}")

            content_parts.append({
                "type": "image_url",
                "image_url": {"url": image_url},
            })

        messages = [{"role": "user", "content": content_parts}]

        try:
            response = client.chat.completions.create(
                model=actual_model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            content = response.choices[0].message.content

            if hasattr(response, "usage") and response.usage:
                logger.info(
                    f"Vision call succeeded – tokens: "
                    f"prompt={response.usage.prompt_tokens}, "
                    f"completion={response.usage.completion_tokens}, "
                    f"total={response.usage.total_tokens}"
                )

            logger.debug(f"Vision response length: {len(content)} chars")
            return content

        except Exception as e:
            logger.error(f"Vision completion failed: {e}")
            raise


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_llm_client_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Return the module-level ``LLMClient`` singleton."""
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = LLMClient()
    return _llm_client_instance


# Backward-compatible aliases
LLMService = LLMClient
get_llm_service = get_llm_client
