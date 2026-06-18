"""LLM 调用重试装饰器：对 retryable 的 Vid2NoteError 做指数退避重试。"""

import logging
from functools import wraps

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from vid2note_core.errors import Vid2NoteError

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    """判断异常是否值得重试（retryable=True 的 Vid2NoteError）。"""
    return isinstance(exc, Vid2NoteError) and exc.retryable


def llm_retry(max_attempts: int = 3):
    """对 retryable 的 LLM 错误重试（限流、超时、临时 API 错误）。

    用法：
        @llm_retry(max_attempts=3)
        def chat(self, messages, ...): ...
    """

    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception(_is_retryable),
            before_sleep=lambda rs: logger.warning(
                "LLM 调用失败（第 %d 次），%ds 后重试: %s",
                rs.attempt_number,
                rs.next_action.sleep,
                rs.outcome.exception(),
            ),
            reraise=True,
        )
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator
