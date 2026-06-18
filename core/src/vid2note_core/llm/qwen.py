"""
通义千问 LLM 实现
使用 OpenAI 兼容接口（阿里云百炼 DashScope）。
"""

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)
from vid2note_core.errors import LLMAPIError, LLMRateLimited, LLMTimeout

from .base import BaseLLM
from .retry import llm_retry

_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class QwenLLM(BaseLLM):
    """通义千问 LLM 实现"""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        **kwargs,
    ):
        super().__init__(api_key, model, **kwargs)
        self.base_url = base_url
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @llm_retry(max_attempts=3)
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        调用通义千问模型。

        Args:
            messages: 消息列表
            **kwargs: 额外参数（temperature, max_tokens, timeout 等）

        Returns:
            模型生成的文本

        Raises:
            LLMRateLimited: 被限流（retryable=True，会被 llm_retry 重试）
            LLMTimeout: 请求超时（retryable=True）
            LLMAPIError: 其他 API 错误（retryable=True）
        """
        timeout = kwargs.get("timeout")
        # 超时通过 request 级参数传入，复用已有 client（保留连接池）
        request_kwargs: dict = {}
        if timeout:
            request_kwargs["timeout"] = timeout

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 4096),
                **request_kwargs,
            )
            return response.choices[0].message.content or ""
        except RateLimitError as e:
            raise LLMRateLimited("qwen") from e
        except APITimeoutError as e:
            raise LLMTimeout("qwen") from e
        except (APIConnectionError, APIStatusError) as e:
            raise LLMAPIError("qwen", str(e)) from e
