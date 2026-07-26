"""
百度文心一言 LLM 实现
使用百度智能云API
"""
import requests
from typing import List, Dict

from .base import BaseLLM


class BaiduLLM(BaseLLM):
    """百度文心一言 LLM 实现"""

    def __init__(self, api_key: str, secret_key: str = "",
                 model: str = "ernie-bot-4",
                 base_url: str = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop",
                 **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.secret_key = secret_key
        self.base_url = base_url
        self.access_token = None
        self._get_access_token()

    def _get_access_token(self):
        """获取百度API访问令牌"""
        try:
            url = f"https://aip.baidubce.com/oauth/2.0/token"
            params = {
                "grant_type": "client_credentials",
                "client_id": self.api_key,
                "client_secret": self.secret_key
            }
            response = requests.post(url, params=params, timeout=30)
            result = response.json()
            self.access_token = result.get("access_token")
            if not self.access_token:
                raise RuntimeError(f"获取百度access_token失败: {result}")
        except Exception as e:
            raise RuntimeError(f"百度认证失败: {str(e)}")

    def _get_model_endpoint(self) -> str:
        """获取模型对应的endpoint"""
        model_map = {
            "ernie-bot-4": "completions_pro",
            "ernie-bot": "completions",
            "ernie-bot-turbo": "eb-instant",
            "ernie-speed": "ernie-speed-128k",
            "ernie-lite": "ernie-lite-8k"
        }
        endpoint = model_map.get(self.model, "completions")
        return f"{self.base_url}/chat/{endpoint}"

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        调用百度文心一言模型

        Args:
            messages: 消息列表
            **kwargs: 额外参数（temperature, max_tokens等）

        Returns:
            模型生成的文本

        Raises:
            RuntimeError: 当API调用失败时
        """
        try:
            url = f"{self._get_model_endpoint()}?access_token={self.access_token}"

            # 转换消息格式
            formatted_messages = []
            for msg in messages:
                role = msg["role"]
                if role == "system":
                    # 百度API不支持system角色，转换为user
                    formatted_messages.append({"role": "user", "content": msg["content"]})
                else:
                    formatted_messages.append({"role": role, "content": msg["content"]})

            payload = {
                "messages": formatted_messages,
                "temperature": kwargs.get('temperature', 0.3),
                "max_output_tokens": kwargs.get('max_tokens', 4096)
            }

            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=kwargs.get('timeout', 120)
            )

            result = response.json()

            if "error_code" in result:
                raise RuntimeError(f"百度API错误: {result.get('error_msg', '未知错误')}")

            return result.get("result", "")

        except requests.exceptions.Timeout:
            raise RuntimeError("百度API请求超时")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"百度API请求失败: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"百度API调用失败: {str(e)}")
