"""
Ollama 本地 LLM 适配器
通过本地 Ollama API 调用本地模型
"""

import os

import httpx

from .base import BaseLLM


class OllamaLLM(BaseLLM):
    """Ollama 本地 LLM 适配器"""

    def __init__(self, api_key: str = "", model: str = "llama3.1", **kwargs):
        # Ollama 不需要 api_key，但保留参数兼容性
        super().__init__(api_key=api_key or "ollama", model=model, **kwargs)
        self.base_url = kwargs.get(
            "base_url", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        )
        self.timeout = kwargs.get("timeout", 120)

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        调用 Ollama /api/chat 接口
        """
        url = f"{self.base_url}/api/chat"
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"无法连接到 Ollama 服务 ({self.base_url})，请确认 Ollama 已启动"
            ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Ollama API 错误: {e.response.status_code} - {e.response.text}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Ollama 请求失败: {e}") from e
