"""
Mock LLM 实现
用于测试环境，避免真实API调用
"""

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

        # 分类请求
        if "分类" in content or "category" in content:
            return '{"category": "knowledge", "confidence": 0.95, "reason": "这是知识点内容"}'

        # 重组/整理请求
        if "重组" in content or "整理" in content or "markdown" in content:
            return self._generate_mock_markdown(messages)

        # 过滤请求
        if "过滤" in content or "filter" in content:
            return '{"should_keep": true, "category": "knowledge", "filtered_text": "过滤后的内容"}'

        # 默认响应
        return "## 整理后的内容\n\n这是Mock LLM生成的测试内容。\n\n### 要点1\n- 内容要点A\n- 内容要点B\n\n### 要点2\n- 内容要点C\n- 内容要点D"

    def _generate_mock_markdown(self, messages) -> str:
        """生成模拟的Markdown内容"""
        return """## 课程笔记整理

### 第一部分：概述

本节主要介绍了RAG（检索增强生成）、Function Calling和MCP（模型上下文协议）的概念和应用。

**核心要点：**
- RAG用于解决大模型预训练数据之外的知识问题
- Function Calling允许大模型调用外部API
- MCP是一种统一的外部系统调用协议

### 第二部分：RAG详解

RAG（Retrieval-Augmented Generation）通过将用户查询与知识库匹配，增强大模型的回答能力。

**适用场景：**
1. 企业内部知识问答
2. 产品文档查询
3. 规章制度检索

### 第三部分：Function Calling

Function Calling让大模型能够调用外部函数获取实时数据。

**典型应用：**
- 订单查询
- 天气查询
- 数据库操作

### 第四部分：MCP协议

MCP（Model Context Protocol）是Anthropic提出的开放标准，用于统一AI与外部系统的集成。

**优势：**
- 统一接口标准
- 降低开发成本
- 提高可维护性

---

*本内容由AI自动生成，仅供参考*"""

    def reset(self):
        """重置计数器"""
        self.call_count = 0
        self.last_messages: list[dict[str, str]] | None = None
