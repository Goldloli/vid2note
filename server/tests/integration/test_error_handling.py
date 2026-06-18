"""测试全局异常处理与 CORS/health 修复。"""

from fastapi.testclient import TestClient
from vid2note_core.errors import LLMError, LLMRateLimited
from vid2note_core.storage.db import Database
from vid2note_server.main import app

client = TestClient(app)


def _reset():
    Database.reset_instance()


def test_vid2note_error_retryable_returns_503():
    """retryable 错误应返回 503。"""
    from fastapi import APIRouter

    _reset()
    test_router = APIRouter()

    @test_router.get("/_test/retryable")
    async def _raise_retryable():
        raise LLMRateLimited("qwen")

    app.include_router(test_router, prefix="/api/v1")
    resp = client.get("/api/v1/_test/retryable")
    assert resp.status_code == 503
    data = resp.json()
    assert data["error"]["retryable"] is True
    assert data["error"]["code"] == "LLM_RATE_LIMITED"


def test_vid2note_error_non_retryable_returns_400():
    """非 retryable 错误应返回 400。"""
    from fastapi import APIRouter

    _reset()
    test_router = APIRouter()

    @test_router.get("/_test/nonretryable")
    async def _raise_non_retryable():
        raise LLMError(
            "密钥缺失",
            code="LLM_API_KEY_MISSING",
            retryable=False,
            user_message="请配置 API Key",
            step="organize",
        )

    app.include_router(test_router, prefix="/api/v1")
    resp = client.get("/api/v1/_test/nonretryable")
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["retryable"] is False
    assert data["message"] == "请配置 API Key"


def test_value_error_returns_422():
    """ValueError（枚举校验失败）应返回 422 而非 500。"""
    _reset()
    resp = client.get("/api/v1/tasks?status=invalid_status_value")
    assert resp.status_code == 422


def test_health_ok():
    """正常情况下 health 返回 200。"""
    _reset()
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
