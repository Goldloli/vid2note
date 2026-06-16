"""
智谱AI GLM LLM 实现
使用 OpenAI 兼容接口
"""

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError

from .base import BaseLLM


class GLMLLM(BaseLLM):
    """智谱AI GLM LLM 实现"""

    def __init__(
        self,
        api_key: str,
        model: str = "glm-4-flash",
        base_url: str = "https://open.bigmodel.cn/api/paas/v4/",
        **kwargs,
    ):
        super().__init__(api_key, model, **kwargs)
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def _process_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """
        处理消息列表，针对特殊模型进行转换

        glm-4.7 模型不支持 system 角色，需要将 system 消息转换为 user 消息
        """
        # 只有 glm-4.7 需要特殊处理
        if self.model != "glm-4.7":
            return messages

        processed = []
        for msg in messages:
            if msg.get("role") == "system":
                # 将 system 角色转换为 user 角色
                processed.append(
                    {"role": "user", "content": f"[系统指令] {msg.get('content', '')}"}
                )
            else:
                processed.append(msg)
        return processed

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        调用 GLM 模型

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
                    base_url="https://open.bigmodel.cn/api/paas/v4/",
                    timeout=timeout,
                )
            else:
                client = self.client

            # 处理消息：glm-4.7 不支持 system 角色，需要转换
            processed_messages = self._process_messages(messages)

            response = client.chat.completions.create(
                model=self.model,
                messages=processed_messages,  # type: ignore[arg-type]
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 4096),
            )

            # 处理响应内容
            message = response.choices[0].message
            content = message.content or ""

            # glm-4.7 等推理模型会将推理过程放在 reasoning_content 中
            # 如果 content 为空，需要从 reasoning_content 中提取最终答案
            if not content and hasattr(message, "reasoning_content") and message.reasoning_content:
                reasoning = message.reasoning_content.strip()
                import re

                # 尝试查找 ```markdown 代码块
                markdown_block_match = re.search(
                    r"```markdown\s*\n(.*?)\n```", reasoning, re.DOTALL
                )
                if markdown_block_match:
                    return markdown_block_match.group(1).strip()

                # 尝试查找任何 ``` 代码块
                code_block_match = re.search(r"```\s*\n(.*?)\n```", reasoning, re.DOTALL)
                if code_block_match:
                    return code_block_match.group(1).strip()

                # 尝试提取 "7. **构建最终回复:**" 或类似标记之后的内容
                patterns = [
                    r"7\.\s*\*\*构建最终回复[:：]\*\*\s*\n?\s*\*?\s*",
                    r"7\.\s*\*\*最终输出[:：]\*\*\s*\n?\s*\*?\s*",
                    r"7\.\s*\*\*最终输出生成[:：]\*\*\s*\n?\s*\*?\s*",
                    r"\*\*最终回复[:：]\*\*\s*\n",
                    r"\*\*最终答案[:：]\*\*\s*\n",
                    r"最终输出[:：]\s*\n",
                    r"7\.\s*\*\*Final Response[:：]\*\*\s*\n?\s*\*?\s*",
                    r"7\.\s*\*\*Final Output[:：]\*\*\s*\n?\s*\*?\s*",
                    r"\*\*Final Answer[:：]\*\*\s*\n",
                ]
                for pattern in patterns:
                    match = re.search(pattern, reasoning, re.IGNORECASE)
                    if match:
                        return reasoning[match.end() :].strip()

                # 如果没找到标记，尝试移除开头的分析部分
                # 查找第一个以 # 开头的行（Markdown 标题）
                first_title_match = re.search(r"\n(# .*)", reasoning)
                if first_title_match:
                    return reasoning[first_title_match.start(1) :].strip()

                # 最后尝试：返回最后一段
                paragraphs = [p.strip() for p in reasoning.split("\n\n") if p.strip()]
                if paragraphs:
                    return paragraphs[-1]
                return reasoning

            return content
        except APIConnectionError as e:
            raise RuntimeError(
                f"GLM API连接错误: 无法连接到服务器，请检查网络连接。{str(e)}"
            ) from e
        except RateLimitError as e:
            raise RuntimeError(f"GLM API速率限制: {str(e)}") from e
        except APITimeoutError as e:
            raise RuntimeError(f"GLM API超时: {str(e)}") from e
        except APIError as e:
            raise RuntimeError(f"GLM API错误: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"GLM API调用失败: {str(e)}") from e
