"""
DeepSeek LLM 实现
使用 OpenAI 兼容接口
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

_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


class DeepSeekLLM(BaseLLM):
    """DeepSeek LLM 实现"""

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = _DEFAULT_BASE_URL,
        **kwargs,
    ):
        super().__init__(api_key, model, **kwargs)
        self.base_url = base_url
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    @llm_retry(max_attempts=3)
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        调用 DeepSeek 模型

        Raises:
            LLMRateLimited / LLMTimeout / LLMAPIError
        """
        timeout = kwargs.get("timeout")
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
            raise LLMRateLimited("deepseek") from e
        except APITimeoutError as e:
            raise LLMTimeout("deepseek") from e
        except (APIConnectionError, APIStatusError) as e:
            raise LLMAPIError("deepseek", str(e)) from e
