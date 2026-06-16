"""
Ollama LLM 适配器测试
"""

import httpx
import pytest
import respx
from vid2note_core.llm.ollama import OllamaLLM


def test_ollama_init_default_url():
    """测试默认 base_url"""
    llm = OllamaLLM(model="llama3.1")
    assert llm.base_url == "http://localhost:11434"
    assert llm.model == "llama3.1"


def test_ollama_init_custom_url():
    """测试自定义 base_url"""
    llm = OllamaLLM(model="qwen2", base_url="http://192.168.1.10:11434")
    assert llm.base_url == "http://192.168.1.10:11434"
    assert llm.model == "qwen2"


def test_ollama_init_from_env(monkeypatch):
    """测试从环境变量读取 base_url"""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.local:11434")
    llm = OllamaLLM(model="llama3")
    assert llm.base_url == "http://ollama.local:11434"


def test_ollama_chat_connect_error():
    """测试连接失败时抛出 ConnectionError（用 respx 模拟连接拒绝，与真实网络环境解耦）"""
    llm = OllamaLLM(model="llama3", base_url="http://localhost:19999")
    with respx.mock(base_url="http://localhost:19999") as mock:
        mock.post("/api/chat").mock(side_effect=httpx.ConnectError("connection refused"))
        with pytest.raises(ConnectionError):
            llm.chat([{"role": "user", "content": "hello"}])


def test_ollama_chat_http_error():
    """测试 HTTP 非 2xx 时抛出 RuntimeError"""
    llm = OllamaLLM(model="llama3", base_url="http://localhost:19999")
    with respx.mock(base_url="http://localhost:19999") as mock:
        mock.post("/api/chat").mock(return_value=httpx.Response(500, text="internal error"))
        with pytest.raises(RuntimeError):
            llm.chat([{"role": "user", "content": "hello"}])


def test_ollama_chat_success():
    """测试正常调用返回 content"""
    llm = OllamaLLM(model="llama3", base_url="http://localhost:19999")
    with respx.mock(base_url="http://localhost:19999") as mock:
        mock.post("/api/chat").mock(
            return_value=httpx.Response(200, json={"message": {"content": "hello back"}})
        )
        result = llm.chat([{"role": "user", "content": "hello"}])
        assert result == "hello back"
