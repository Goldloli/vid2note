"""
MiniMax LLM 实现
"""

import requests

from .base import BaseLLM


class MiniMaxLLM(BaseLLM):
    """MiniMax LLM 实现"""

    def __init__(
        self,
        api_key: str,
        group_id: str = "",
        model: str = "abab6.5-chat",
        base_url: str = "https://api.minimax.chat/v1",
        **kwargs,
    ):
        super().__init__(api_key, model, **kwargs)
        self.group_id = group_id
        self.base_url = base_url

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        调用 MiniMax 模型

        Args:
            messages: 消息列表
            **kwargs: 额外参数（temperature, max_tokens, timeout等）

        Returns:
            模型生成的文本

        Raises:
            RuntimeError: 当API调用失败时
        """
        try:
            url = f"{self.base_url}/text/chatcompletion_v2"

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # 转换消息格式
            formatted_messages = []
            system_content = ""
            for msg in messages:
                if msg["role"] == "system":
                    system_content = msg["content"]
                else:
                    formatted_messages.append({"role": msg["role"], "content": msg["content"]})

            payload = {
                "model": self.model,
                "messages": formatted_messages,
                "temperature": kwargs.get("temperature", 0.3),
                "max_tokens": kwargs.get("max_tokens", 4096),
            }

            # 如果有system消息，添加到prompt
            if system_content:
                payload["prompt"] = system_content

            response = requests.post(
                url, headers=headers, json=payload, timeout=kwargs.get("timeout", 120)
            )

            result = response.json()

            if result.get("base_resp", {}).get("status_code") != 0:
                error_msg = result.get("base_resp", {}).get("status_msg", "未知错误")
                raise RuntimeError(f"MiniMax API错误: {error_msg}")
            choices = result.get("choices", [])
            if choices and len(choices) > 0:
                message = choices[0].get("message", {})
                return message.get("content", "")

            return ""

        except requests.exceptions.Timeout:
            raise RuntimeError("MiniMax API请求超时") from None
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"MiniMax API请求失败: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"MiniMax API调用失败: {str(e)}") from e
