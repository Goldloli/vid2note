"""智谱 GLM OpenAI 兼容适配器。"""
from __future__ import annotations

from typing import Dict, List

from .openai_compatible import OpenAICompatibleLLM


class GLMLLM(OpenAICompatibleLLM):
    provider_label = "GLM"
    default_model = "glm-5.2"
    default_base_url = "https://open.bigmodel.cn/api/paas/v4/"

    def prepare_messages(
        self, messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        # 保留旧版 glm-4.7 的角色兼容处理，不影响当前默认模型。
        if self.model != "glm-4.7":
            return messages
        return [
            {
                "role": "user" if item.get("role") == "system" else item.get("role"),
                "content": (
                    f"[系统指令] {item.get('content', '')}"
                    if item.get("role") == "system"
                    else item.get("content", "")
                ),
            }
            for item in messages
        ]
