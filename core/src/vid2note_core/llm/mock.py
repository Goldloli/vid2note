"""
Mock LLM 实现
用于测试环境，避免真实API调用
"""

import re

from .base import BaseLLM


class MockLLM(BaseLLM):
    """Mock LLM 实现 - 用于测试"""

    def __init__(self, api_key: str = "mock_key", model: str = "mock_model", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self.call_count = 0
        self.last_messages: list[dict[str, str]] | None = None

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        模拟聊天调用

        Args:
            messages: 消息列表
            **kwargs: 额外参数

        Returns:
            模拟的响应文本
        """
        self.call_count += 1
        self.last_messages = messages

        # 根据消息内容返回不同的模拟响应
        content = str(messages).lower()

        if "思维导图" in content or "mindmap" in content:
            return "mindmap\n  root((来源笔记))\n    内容要点\n    证据说明"

        # 重组/整理请求
        if "重组" in content or "整理" in content or "markdown" in content:
            return self._generate_mock_markdown(messages)

        # 分类请求
        if "分类" in content or "category" in content:
            return '{"category": "knowledge", "confidence": 0.95, "reason": "这是知识点内容"}'

        # 过滤请求
        if "过滤" in content or "filter" in content:
            return '{"should_keep": true, "category": "knowledge", "filtered_text": "过滤后的内容"}'

        # 默认响应
        return "## 整理后的内容\n\n这是Mock LLM生成的测试内容。\n\n### 要点1\n- 内容要点A\n- 内容要点B\n\n### 要点2\n- 内容要点C\n- 内容要点D"

    def _generate_mock_markdown(self, messages) -> str:
        """把固定 SRT 输入转为可核验、无补充事实的来源笔记。"""
        user_content = next(
            (message["content"] for message in messages if message.get("role") == "user"), ""
        )
        if "字幕：\n" in user_content:
            user_content = user_content.split("字幕：\n", 1)[1]
        if "\n\n转换为" in user_content:
            user_content = user_content.rsplit("\n\n转换为", 1)[0]

        segments = re.findall(
            r"\d+\s*\n"
            r"(\d{2}:\d{2}:\d{2}),\d{3}\s+-->\s+"
            r"(\d{2}:\d{2}:\d{2}),\d{3}\s*\n"
            r"(.+?)(?=\n\s*\n\d+\s*\n|\Z)",
            user_content,
            flags=re.DOTALL,
        )
        lines = ["# 来源笔记", "", "## 内容要点", ""]
        for start, end, raw_text in segments:
            text = " ".join(raw_text.split())
            uncertainty = " **ASR 不确定：**" if "[听不清]" in text else ""
            lines.append(f"-{uncertainty} {text}（证据：{start}–{end}）")
        lines.extend(
            [
                "",
                "## 证据说明",
                "",
                "以上内容仅重排字幕原文；时间范围来自对应 SRT 片段。",
            ]
        )
        return "\n".join(lines)

    def reset(self):
        """重置计数器"""
        self.call_count = 0
        self.last_messages: list[dict[str, str]] | None = None
