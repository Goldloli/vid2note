"""
通义千问 LLM 实现
使用 OpenAI 兼容接口
"""
from typing import List, Dict
from openai import OpenAI, RateLimitError, APITimeoutError, APIError, APIConnectionError

from .base import BaseLLM


class QwenLLM(BaseLLM):
    """通义千问 LLM 实现"""
    
    def __init__(self, api_key: str, model: str, base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url
        )
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        调用通义千问模型

        Args:
            messages: 消息列表
            **kwargs: 额外参数（temperature, max_tokens, timeout等）

        Returns:
            模型生成的文本

        Raises:
            RuntimeError: 当API调用失败时
        """
        try:
            # 从kwargs中提取客户端参数
            client_kwargs = {}
            timeout = kwargs.get('timeout')
            if timeout:
                client_kwargs['timeout'] = timeout

            # 创建客户端（如果需要自定义超时）
            if client_kwargs:
                from openai import OpenAI
                client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    **client_kwargs
                )
            else:
                client = self.client

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get('temperature', 0.3),
                max_tokens=kwargs.get('max_tokens', 4096)
            )
            return response.choices[0].message.content
        except APIConnectionError as e:
            raise RuntimeError(f"Qwen API连接错误: 无法连接到服务器，请检查网络连接。{str(e)}")
        except RateLimitError as e:
            raise RuntimeError(f"Qwen API速率限制: {str(e)}")
        except APITimeoutError as e:
            raise RuntimeError(f"Qwen API超时: {str(e)}")
        except APIError as e:
            raise RuntimeError(f"Qwen API错误: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Qwen API调用失败: {str(e)}")
