"""
字节豆包 LLM 实现
使用 OpenAI 兼容接口
"""

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from .base import BaseLLM


class DoubaoLLM(BaseLLM):
    """字节豆包 LLM 实现"""

    def __init__(
        self,
        api_key: str,
        model: str = "doubao-pro-4k",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        **kwargs,
    ):
        super().__init__(api_key, model, **kwargs)
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        调用豆包模型

        Args:
            messages: 消息列表
            **kwargs: 额外参数（temperature, max_tokens, timeout等）

        Returns:
            模型生成的文本

        Raises:
            RuntimeError: 当API调用失败时
        """
        try:
            timeout = kwargs.get("timeout")
            if timeout:
                from openai import OpenAI

                client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://ark.cn-beijing.volces.com/api/v3",
                    timeout=timeout,
                )
            else:
                client = self.client

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 4096),
            )
            return response.choices[0].message.content or ""
        except APIConnectionError as e:
            raise RuntimeError(
                f"豆包API连接错误: 无法连接到服务器，请检查网络连接。{str(e)}"
            ) from e
        except RateLimitError as e:
            raise RuntimeError(f"豆包API速率限制: {str(e)}") from e
        except APITimeoutError as e:
            raise RuntimeError(f"豆包API超时: {str(e)}") from e
        except APIError as e:
            raise RuntimeError(f"豆包API错误: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"豆包API调用失败: {str(e)}") from e
