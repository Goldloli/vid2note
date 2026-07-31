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


def _safe_int(value: Any) -> int:
    """把 usage 数值字段安全转为 int(缺失/非法值归 0)。"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def normalize_usage(usage: Any) -> Dict[str, int] | None:
    """把各家 provider 的响应 usage 归一化为固定字段 dict(openspec「LLM 用量观测」)。

    产出 ``{prompt_tokens, completion_tokens, cache_hit_tokens, cache_miss_tokens}``:
    - DeepSeek 顶层 ``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens`` 直接采用;
    - OpenAI 系取嵌套 ``usage.prompt_tokens_details.cached_tokens`` 作为命中,
      未命中按 ``prompt_tokens - cache_hit`` 兜底;
    - 无任何缓存字段时命中记 0、未命中记全部输入;
    - ``usage`` 为 None 时返回 None(本地模型 / mock 无用量场景)。

    全部取值经 getattr + _safe_int 防御,本函数不抛异常。
    """
    if usage is None:
        return None
    prompt_tokens = _safe_int(getattr(usage, "prompt_tokens", 0))
    completion_tokens = _safe_int(getattr(usage, "completion_tokens", 0))
    cache_hit = getattr(usage, "prompt_cache_hit_tokens", None)
    cache_miss = getattr(usage, "prompt_cache_miss_tokens", None)
    if cache_hit is None:
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cache_hit = getattr(details, "cached_tokens", None)
    cache_hit = _safe_int(cache_hit)
    cache_miss = _safe_int(cache_miss) if cache_miss is not None else prompt_tokens - cache_hit
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cache_hit_tokens": cache_hit,
        "cache_miss_tokens": cache_miss,
    }


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
        # 最近一次 chat() 的归一化用量(None 表示尚未调用或无用量)
        self.last_usage: Dict[str, int] | None = None
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
            # DeepSeek-v4 默认开思考模式，复杂任务思考会很长、耗尽 max_tokens 使答案
            # (content) 来不及生成；vid2note 的 prompt 工程已给明确指令，关思考让模型
            # 直接输出答案。实测 thinking={"type":"disabled"}（或 reasoning_effort=none）
            # 可关；enable_thinking 无效。其他 provider 不含 deepseek base_url 时传空。
            extra_body = {"thinking": {"type": "disabled"}} if "deepseek" in (self.base_url or "").lower() else {}
            response = client.chat.completions.create(**request, extra_body=extra_body)
            # 暂存本次调用的归一化用量(消费方须在下次 chat 前读取;全部调用串行)
            self.last_usage = normalize_usage(getattr(response, "usage", None))
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


__all__ = ["OpenAICompatibleLLM", "normalize_usage"]
