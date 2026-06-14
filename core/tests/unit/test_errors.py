"""测试错误体系"""
import pytest
from vid2note_core.errors import (
    Vid2NoteError, DownloadError, DownloadURLInvalid, DownloadCookieExpired,
    ASRError, ASRToolBChanged, LLMError, LLMRateLimited, PipelineError,
)


def test_base_error_fields():
    e = Vid2NoteError("test", code="TEST", retryable=True, user_message="msg")
    assert e.code == "TEST"
    assert e.retryable is True
    assert e.user_message == "msg"


def test_download_url_invalid():
    e = DownloadURLInvalid("bad url")
    assert e.code == "DOWNLOAD_URL_INVALID"
    assert e.retryable is False


def test_download_cookie_expired():
    e = DownloadCookieExpired()
    assert e.code == "DOWNLOAD_COOKIE_EXPIRED"
    assert e.user_message == "Cookie 已过期，请到设置页更新"


def test_asr_tool_b_changed():
    e = ASRToolBChanged("response structure changed")
    assert e.code == "ASRTOOL_B_CHANGED"
    assert e.retryable is False


def test_llm_rate_limited():
    e = LLMRateLimited("qwen")
    assert e.code == "LLM_RATE_LIMITED"
    assert e.retryable is True


def test_error_to_dict():
    e = DownloadURLInvalid("bad")
    d = e.to_dict()
    assert d["code"] == "DOWNLOAD_URL_INVALID"
    assert d["retryable"] is False
    assert "message" in d


def test_all_error_codes_unique():
    """所有错误码不重复"""
    codes = [
        DownloadURLInvalid("x").code,
        DownloadCookieExpired().code,
        ASRToolBChanged("x").code,
        LLMRateLimited("x").code,
    ]
    assert len(codes) == len(set(codes))
