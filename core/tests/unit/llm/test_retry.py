"""测试 LLM 重试与错误类型透传。"""

from unittest.mock import MagicMock

import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError
from vid2note_core.errors import LLMAPIError, LLMRateLimited, LLMTimeout
from vid2note_core.llm.qwen import QwenLLM


def _make_rate_limit_error():
    return RateLimitError(message="rate limited", response=MagicMock(), body=None)


def _make_timeout_error():
    return APITimeoutError(request=MagicMock())


def _make_conn_error():
    return APIConnectionError(request=MagicMock())


def test_rate_limit_raises_retryable_error():
    """限流时应抛 LLMRateLimited（retryable=True）。"""
    llm = QwenLLM(api_key="sk-test", model="qwen-turbo")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _make_rate_limit_error()
    llm.client = mock_client
    with pytest.raises(LLMRateLimited) as exc_info:
        llm.chat([{"role": "user", "content": "hi"}])
    assert exc_info.value.retryable is True


def test_timeout_raises_retryable_error():
    """超时应抛 LLMTimeout（retryable=True）。"""
    llm = QwenLLM(api_key="sk-test", model="qwen-turbo")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _make_timeout_error()
    llm.client = mock_client
    with pytest.raises(LLMTimeout) as exc_info:
        llm.chat([{"role": "user", "content": "hi"}])
    assert exc_info.value.retryable is True


def test_connection_error_raises_llm_api_error():
    """连接错误应抛 LLMAPIError（retryable=True）。"""
    llm = QwenLLM(api_key="sk-test", model="qwen-turbo")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _make_conn_error()
    llm.client = mock_client
    with pytest.raises(LLMAPIError) as exc_info:
        llm.chat([{"role": "user", "content": "hi"}])
    assert exc_info.value.retryable is True


def test_retry_then_success():
    """第一次限流、第二次成功，应重试后返回结果。"""
    llm = QwenLLM(api_key="sk-test", model="qwen-turbo")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="ok"))]
    mock_client.chat.completions.create.side_effect = [
        _make_rate_limit_error(),
        mock_resp,
    ]
    llm.client = mock_client
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result == "ok"
    assert mock_client.chat.completions.create.call_count == 2


def test_retry_exhausted_after_max_attempts():
    """连续限流超过最大重试次数后应抛 LLMRateLimited。"""
    llm = QwenLLM(api_key="sk-test", model="qwen-turbo")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _make_rate_limit_error()
    llm.client = mock_client
    with pytest.raises(LLMRateLimited):
        llm.chat([{"role": "user", "content": "hi"}])
    # max_attempts=3，应调用 3 次
    assert mock_client.chat.completions.create.call_count == 3
