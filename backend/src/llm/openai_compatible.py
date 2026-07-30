"""OpenAI Chat Completions 兼容适配器基类。"""
from __future__ import annotations

from typing import Any, Dict, List

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from .base import BaseLLM


class OpenAICompatibleLLM(BaseLLM):
    """统一处理 Base URL、timeout、错误和 Chat Completions 请求。"""

    provider_label = "LLM"
    default_model = ""
    default_base_url = ""
    default_api_key = ""
    requires_model = True
    requires_base_url = True

    def __init__(
        self,
        api_key: str = "",
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 120,
        **kwargs: Any,
    ) -> None:
        resolved_model = str(
            self.default_model if model is None else model
        ).strip()
        resolved_base_url = str(
            self.default_base_url if base_url is None else base_url
        ).strip().rstrip("/")
        if self.requires_model and not resolved_model:
            raise ValueError("model 不能为空")
        if self.requires_base_url and not resolved_base_url:
            raise ValueError("base_url 不能为空")
        resolved_key = str(api_key or self.default_api_key)
        super().__init__(resolved_key, resolved_model, **kwargs)
        self.base_url = resolved_base_url
        self.timeout = float(timeout)
        self.client = OpenAI(
            api_key=resolved_key or "not-required",
            base_url=self.base_url,
            timeout=self.timeout,
        )

    def prepare_messages(
        self, messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        return messages

    def extract_content(self, response: Any) -> str:
        message = response.choices[0].message
        content = getattr(message, "content", None)
        if content:
            return str(content)
        reasoning = getattr(message, "reasoning_content", None)
        return str(reasoning or "")

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        try:
            timeout = kwargs.get("timeout")
            client = (
                self.client.with_options(timeout=float(timeout))
                if timeout is not None
                else self.client
            )
            request: dict[str, Any] = {
                "model": self.model,
                "messages": self.prepare_messages(messages),
                "max_tokens": kwargs.get("max_tokens", 4096),
            }
            if kwargs.get("temperature") is not None:
                request["temperature"] = kwargs["temperature"]
            else:
                request["temperature"] = 0.3
            response = client.chat.completions.create(**request)
            return self.extract_content(response)
        except APIConnectionError as exc:
            raise RuntimeError(f"{self.provider_label} 连接失败") from exc
        except RateLimitError as exc:
            raise RuntimeError(f"{self.provider_label} 请求频率受限") from exc
        except APITimeoutError as exc:
            raise RuntimeError(f"{self.provider_label} 请求超时") from exc
        except APIError as exc:
            raise RuntimeError(f"{self.provider_label} API 错误：{exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"{self.provider_label} 调用失败：{exc}") from exc


__all__ = ["OpenAICompatibleLLM"]
