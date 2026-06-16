"""
LLM 抽象基类
定义统一的 LLM 接口
"""

import re
from abc import ABC, abstractmethod
from typing import Any


class BaseLLM(ABC):
    """LLM基类，统一接口"""

    def __init__(self, api_key: str, model: str, **kwargs):
        self.api_key = api_key
        self.model = model
        self.kwargs = kwargs

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        通用对话接口

        Args:
            messages: 消息列表，格式 [{"role": "system/user/assistant", "content": "..."}]
            **kwargs: 额外参数

        Returns:
            模型返回的文本内容
        """
        pass

    def _estimate_tokens(self, text: str) -> int:
        """估算token数（中文字符按1.5个token，英文按1个token）"""
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars)

    def restructure_content(
        self, subtitle: str, context: str = "", temperature: float = 0.3
    ) -> str:
        """
        重组内容为标准Markdown格式
        策略：完全不分块，一次性发送，但限制输出长度以加快速度

        Args:
            subtitle: 字幕文本
            context: 上下文信息（如章节标题）
            temperature: 温度参数

        Returns:
            重组后的Markdown文本
        """
        total_tokens = self._estimate_tokens(subtitle)
        print(f"处理内容（约{total_tokens} tokens），快速模式...")

        try:
            # 快速模式：2分钟超时，限制输出长度
            return self._process_single_block_fast(subtitle, context, temperature)
        except Exception as e:
            print(f"LLM处理失败: {e}")
            return self._simple_format(subtitle)

    def _process_single_block_fast(self, content: str, context: str, temperature: float) -> str:
        """处理单块内容，平衡质量和速度"""
        system_prompt = self._load_prompt("restructure")

        if system_prompt is None:
            system_prompt = """将课程字幕转换为结构化的Markdown笔记。去除口语化，保留核心知识点和数据。使用表格、列表、加粗等格式。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"章节：{context}\n\n字幕：\n{content}\n\n转换为详细且结构清晰的Markdown笔记：",
            },
        ]

        try:
            # 平衡模式：减少token和超时以加快速度
            return self.chat(messages, temperature=0.3, max_tokens=3000, timeout=60)
        except Exception as e:
            print(f"处理失败: {e}")
            return self._simple_format(content)

    def _simple_format(self, content: str) -> str:
        """简单格式化"""
        filler_words = ["嗯", "啊", "哦", "呃", "哎", "那个", "这个", "就是", "对吧", "是吧"]
        result = content
        for word in filler_words:
            result = result.replace(word, "")
        result = re.sub(r"\s+", " ", result)
        result = re.sub(r"([。！？])\s*", r"\1\n", result)
        return result.strip()

    def _load_prompt(self, prompt_name: str) -> str | None:
        """从文件加载提示词"""
        import os

        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "prompts",
            f"{prompt_name}.txt",
        )
        try:
            with open(prompt_path, encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None

    def classify_content(self, text: str, temperature: float = 0.3) -> dict[str, Any]:
        """分类内容类型（闲聊/知识/过渡）"""
        estimated_tokens = self._estimate_tokens(text)
        if estimated_tokens > 1000:
            text = text[:700]

        messages = [
            {
                "role": "system",
                "content": """你是一个内容分类专家。请将输入的文本分类为以下三类之一：
- "chat": 闲聊内容（问候、过渡语、口语化表达、与课程无关的内容）
- "knowledge": 知识内容（概念解释、技术细节、知识点讲解）
- "transition": 过渡内容（章节转换、话题切换、承上启下）

请以JSON格式返回结果：
{
    "category": "chat/knowledge/transition",
    "confidence": 0.0-1.0,
    "reason": "分类理由"
}""",
            },
            {"role": "user", "content": f"请分类以下文本：\n\n{text}"},
        ]

        try:
            response = self.chat(messages, temperature=temperature)
            import json

            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]

            result = json.loads(json_str.strip())
            return result
        except Exception as e:
            return {"category": "knowledge", "confidence": 0.5, "reason": f"解析失败: {str(e)}"}
