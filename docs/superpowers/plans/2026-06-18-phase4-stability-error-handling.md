# Phase 4: 稳定性与错误处理 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除系统在失败时"假装成功"的核心问题（mock ASR 兜底、_simple_format LLM 兜底、MockLLM 默认），补上 LLM 重试/超时、worker 信号处理/优雅关闭、错误类型透传到 HTTP，让失败可见、可重试、可诊断。

**Architecture:** 分四条线推进：(A) 移除掩盖失败的兜底逻辑，改为显式失败；(B) LLM 层加重试（tenacity）+ 真实错误类型透传；(C) worker 加信号处理、子进程超时、task 重试；(D) server 加全局异常处理器把 Vid2NoteError 翻译为正确 HTTP 状态码。

**Tech Stack:** tenacity（重试库）、Python signal 模块、FastAPI exception_handler。

**前提：** Phase 1-3 完成。需新增依赖 `tenacity`（加到 core/pyproject.toml）。

---

## 文件结构（改动清单）

- Modify: `core/pyproject.toml` — 加 tenacity 依赖
- Modify: `core/src/vid2note_core/pipeline/real_nodes.py` — 移除 _default_asr/_default_llm 的 mock 兜底，改为显式抛错
- Modify: `core/src/vid2note_core/llm/qwen.py` (+ glm/deepseek 等同类) — 包 tenacity 重试 + 抛 LLMRateLimited/LLMTimeout
- Modify: `core/src/vid2note_core/llm/base.py` — 移除 _simple_format 兜底
- Modify: `core/src/vid2note_core/worker.py` — 加信号处理、task 重试、超时
- Modify: `core/src/vid2note_core/downloaders/bbdown.py` (+ ytdlp) — subprocess 加 timeout
- Modify: `server/src/vid2note_server/main.py` — 加全局 exception_handler 翻译 Vid2NoteError
- Modify: `server/src/vid2note_server/main.py` — 修 CORS（去掉 allow_origins=* 或关 allow_credentials）
- Create: 相应测试

---

## Task 1: 移除 mock ASR 兜底（Critical）

`real_nodes.py:_default_asr` 捕获所有异常返回 `_MockASR`（产出"[mock] 示例转录文本"），任务假成功。改为显式抛 ASRError。

**Files:**
- Modify: `core/src/vid2note_core/pipeline/real_nodes.py`

- [ ] **Step 1: 定位 _default_asr**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && grep -n "_default_asr\|_MockASR\|except Exception.*mock\|示例转录文本" core/src/vid2note_core/pipeline/real_nodes.py`

- [ ] **Step 2: 替换 _default_asr 为显式失败**

找到 `_default_asr` 方法（约 460-481 行），把 `except Exception: return _MockASR()` 改为：

```python
def _default_asr(self, config: dict):
    """从配置创建 ASR，失败时抛错（不再静默回退 mock）。"""
    provider = config.get("asr_provider", "asrtools-b")
    try:
        return ASRFactory.create(provider, config)
    except ValueError as e:
        # provider 名错误或后端不支持
        raise ASRError(
            f"不支持的 ASR 提供商: {provider}（{e}）",
            code="ASR_PROVIDER_INVALID",
            retryable=False,
            user_message=f"ASR 提供商 {provider} 不可用，请到设置页检查",
            step="transcribe",
        ) from e
    except Exception as e:
        raise ASRError(
            f"ASR 初始化失败: {e}",
            code="ASR_INIT_FAILED",
            retryable=True,
            user_message=f"语音识别初始化失败：{e}",
            step="transcribe",
        ) from e
```

（删除 `_MockASR` 内部类。）

- [ ] **Step 3: 同样移除 _default_llm 的 mock 兜底**

找到 `_default_llm`（约 480-490 行），改为抛 LLMError 而非返回 MockLLM：

```python
def _default_llm(self, config: dict):
    provider = config.get("llm_provider", "qwen")
    api_key = config.get("api_key", "")
    if not api_key:
        raise LLMError(
            f"LLM provider {provider} 缺少 API Key",
            code="LLM_API_KEY_MISSING",
            retryable=False,
            user_message=f"未配置 {provider} 的 API Key，请到设置页填写",
            step="organize",
        )
    try:
        return LLMFactory.create(provider, {"api_key": api_key, "model": config.get("llm_model")})
    except Exception as e:
        raise LLMError(
            f"LLM 初始化失败: {e}",
            code="LLM_INIT_FAILED",
            retryable=False,
            user_message=f"AI 服务初始化失败：{e}",
            step="organize",
        ) from e
```

- [ ] **Step 4: 更新现有测试**

`core/tests/unit/pipeline/test_real_nodes.py` 里依赖 mock 兜底的测试会失败。改为传入正常 mock 的 ASR/LLM（已有的 fake_asr/fake_llm fixture），删除断言"[mock]"的用例。

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest core/tests/unit/pipeline/test_real_nodes.py -v 2>&1 | tail -10`
修复失败的用例（让其显式传入 asr/llm 或断言抛 ASRError/LLMError）。

- [ ] **Step 5: 加新测试：provider 缺失时抛错**

```python
def test_default_asr_invalid_provider_raises():
    """asr_provider 错误时应抛 ASRError 而非回退 mock。"""
    from vid2note_core.errors import ASRError
    node = RealTranscribeNode()
    with pytest.raises(ASRError, match="不支持的 ASR 提供商"):
        node._default_asr({"asr_provider": "nonexistent"})


def test_default_llm_missing_key_raises():
    """api_key 缺失时应抛 LLMError 而非回退 mock。"""
    from vid2note_core.errors import LLMError
    node = RealOrganizeNode()
    with pytest.raises(LLMError, match="缺少 API Key"):
        node._default_llm({"llm_provider": "qwen", "api_key": ""})
```

- [ ] **Step 6: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add core/src/vid2note_core/pipeline/real_nodes.py core/tests/unit/pipeline/test_real_nodes.py
git commit -m "fix(pipeline): 移除 mock ASR/LLM 兜底，失败时显式抛错（不再假成功）"
```

---

## Task 2: 移除 LLM _simple_format 兜底（Critical）

`llm/base.py:restructure_content` 在 chat() 抛错时 print 一下就返回用正则删语气词的原文，任务假成功。改为让异常向上传播。

**Files:**
- Modify: `core/src/vid2note_core/llm/base.py`

- [ ] **Step 1: 定位兜底逻辑**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && grep -n "_simple_format\|LLM处理失败\|except.*chat\|print(" core/src/vid2note_core/llm/base.py`

- [ ] **Step 2: 移除 restructure_content 的 try/except 兜底**

找到 `restructure_content`（约 50-95 行），移除包住 `self.chat(...)` 的 `try/except`，让异常直接传播。保留 `_simple_format` 方法定义（可能被显式调用），但不在异常路径调用它。

```python
def restructure_content(self, content: str, ...) -> str:
    """用 LLM 把字幕重组为 markdown 笔记。失败时抛 LLMError，不静默兜底。"""
    # ... token 估算、分块逻辑 ...
    for block in blocks:
        result = self.chat(
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": block}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # 移除 try/except，让 RateLimitError/TimeoutError/APIError 向上传播
        output.append(result)
    return "\n\n".join(output)
```

同时把 `print(...)` 换成 `logging.getLogger(__name__).info(...)`。

- [ ] **Step 3: 移除 chat() 的 broad except（若存在）**

检查各 LLM 适配器的 `chat` 方法，确保 RateLimitError/TimeoutError 不被包成 RuntimeError（见 Task 3）。

- [ ] **Step 4: 更新测试**

若有测试断言 `_simple_format` 被调用，改为断言抛 LLMError。

- [ ] **Step 5: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add core/src/vid2note_core/llm/base.py core/tests/
git commit -m "fix(llm): 移除 restructure_content 的 _simple_format 兜底（失败不再假成功）"
```

---

## Task 3: LLM 适配器抛真实错误类型 + 加重试（High）

各 LLM chat() 把所有异常包成 RuntimeError，丢失了 LLMRateLimited(retryable=True) 等类型。改为按异常类型抛对应的 Vid2NoteError，并对 retryable 错误加 tenacity 重试。

**Files:**
- Modify: `core/pyproject.toml` — 加 tenacity
- Modify: `core/src/vid2note_core/llm/qwen.py`（+ glm/deepseek/moonshot/doubao 同类改法）
- Create: `core/src/vid2note_core/llm/retry.py` — 共享重试装饰器

- [ ] **Step 1: 加 tenacity 依赖**

`core/pyproject.toml` dependencies 列表加 `"tenacity>=8.2,<9",`。

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/pip install tenacity && .venv/bin/pip install -e core/`

- [ ] **Step 2: 创建共享重试装饰器**

`core/src/vid2note_core/llm/retry.py`:

```python
"""LLM 调用重试装饰器：对 retryable 的 Vid2NoteError 做指数退避重试。"""

import logging
from functools import wraps

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
)

from vid2note_core.errors import Vid2NoteError

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, Vid2NoteError) and exc.retryable


def llm_retry(max_attempts: int = 3):
    """对 retryable 的 LLM 错误重试（限流、超时、临时 API 错误）。"""

    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception(_is_retryable),
            before_sleep=lambda rs: logger.warning(
                "LLM 调用失败（第 %d 次），%ds 后重试: %s",
                rs.attempt_number, rs.next_action.sleep, rs.outcome.exception(),
            ),
            reraise=True,
        )
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator
```

- [ ] **Step 3: 重写 qwen.py chat() 抛真实错误 + 加重试**

替换 qwen.py 的 chat()（约 40-75 行）：

```python
import logging
from openai import OpenAI, RateLimitError, APITimeoutError, APIConnectionError, APIStatusError

from vid2note_core.errors import LLMRateLimited, LLMTimeout, LLMAPIError
from vid2note_core.llm.retry import llm_retry

logger = logging.getLogger(__name__)


class QwenLLM(BaseLLM):
    # ... __init__ 不变 ...

    @llm_retry(max_attempts=3)
    def chat(self, messages, temperature=0.3, max_tokens=4096, timeout=60):
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            return resp.choices[0].message.content or ""
        except RateLimitError as e:
            raise LLMRateLimited("qwen") from e
        except APITimeoutError as e:
            raise LLMTimeout("qwen") from e
        except (APIConnectionError, APIStatusError) as e:
            raise LLMAPIError("qwen", str(e)) from e
        # 不再用 except Exception: raise RuntimeError
```

- [ ] **Step 4: 对 glm/deepseek/moonshot/doubao 做相同改造**

这几个文件结构类似（都基于 OpenAI SDK 或 requests），按同样模式改：RateLimitError→LLMRateLimited、Timeout→LLMTimeout、其他→LLMAPIError。每个文件加 `@llm_retry()`。

- [ ] **Step 5: 写测试（mock openai 验证错误类型）**

`core/tests/unit/llm/test_retry.py`:

```python
"""测试 LLM 重试与错误类型透传。"""

from unittest.mock import MagicMock, patch
import pytest
from vid2note_core.errors import LLMRateLimited, LLMTimeout
from vid2note_core.llm.qwen import QwenLLM


def test_rate_limit_raises_retryable_error():
    """限流时应抛 LLMRateLimited（retryable=True）。"""
    from openai import RateLimitError
    llm = QwenLLM(api_key="sk-test", model="qwen-turbo")
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RateLimitError(
        message="rate limited", response=MagicMock(), body=None
    )
    llm.client = mock_client
    with pytest.raises(LLMRateLimited) as exc_info:
        llm.chat([{"role": "user", "content": "hi"}])
    assert exc_info.value.retryable is True


def test_retry_then_success():
    """第一次限流、第二次成功，应重试后返回结果。"""
    llm = QwenLLM(api_key="sk-test", model="qwen-turbo")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="ok"))]
    mock_client.chat.completions.create.side_effect = [
        RateLimitError(message="rl", response=MagicMock(), body=None),
        mock_resp,
    ]
    llm.client = mock_client
    result = llm.chat([{"role": "user", "content": "hi"}])
    assert result == "ok"
    assert mock_client.chat.completions.create.call_count == 2
```

- [ ] **Step 6: 运行测试 + Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/python -m pytest core/tests/unit/llm/ -v 2>&1 | tail -10
git add core/pyproject.toml core/src/vid2note_core/llm/ core/tests/unit/llm/
git commit -m "feat(llm): 抛真实错误类型(LLMRateLimited等)+tenacity重试（不再包成RuntimeError）"
```

---

## Task 4: worker 加信号处理 + task 重试（High）

**Files:**
- Modify: `core/src/vid2note_core/worker.py`

- [ ] **Step 1: 加信号处理（SIGTERM/SIGINT 优雅关闭）**

在 worker 启动时注册信号处理，停止时等待 in-flight 任务：

```python
import signal

class TaskWorker:
    async def start(self):
        self._task = asyncio.create_task(self._run())
        # 注册信号处理
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

    async def stop(self):
        if self._task and not self._task.done():
            self._running = False
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=30)  # 等 in-flight 最多 30s
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
```

- [ ] **Step 2: task 失败时按 retryable 决定是否重试**

在 `_process` 的 except 分支：

```python
except Exception as e:
    retryable = isinstance(e, Vid2NoteError) and e.retryable
    attempt = task.retry_count or 0
    max_retries = 3
    if retryable and attempt < max_retries:
        logger.warning("任务 %s 第 %d 次失败（retryable），稍后重试", task_id, attempt + 1)
        repo.update(task_id, status=TaskStatus.PENDING, retry_count=attempt + 1)
        await asyncio.sleep(2 ** attempt)  # 指数退避
    else:
        repo.update(task_id, status=TaskStatus.FAILED, error_message=str(e))
        get_event_bus().publish(TaskEvent(task_id, "task.failed", str(e), progress=0))
```

（需在 task_repo 加 retry_count 字段——已存在则直接用。）

- [ ] **Step 3: 启动时恢复卡在 RUNNING 的任务**

在 worker 启动时扫描 status=RUNNING 但进程已重启的任务，重置为 PENDING：

```python
async def _recover_stale_tasks(self):
    """启动时把上次崩溃留下的 RUNNING 任务重置为 PENDING。"""
    repo = TaskRepository()
    stale = repo.list_all(status=TaskStatus.RUNNING, limit=100)
    for task in stale:
        logger.warning("恢复残留 RUNNING 任务: %s", task.task_id)
        repo.update(task.task_id, status=TaskStatus.PENDING)
```

在 `start()` 里 `await self._recover_stale_tasks()` 后再启动循环。

- [ ] **Step 4: 写测试 + Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/python -m pytest core/tests/unit/test_worker.py -v 2>&1 | tail -10
git add core/src/vid2note_core/worker.py core/tests/
git commit -m "feat(worker): 信号处理+优雅关闭+retryable重试+启动恢复残留任务"
```

---

## Task 5: 下载器 subprocess 加超时（High）

**Files:**
- Modify: `core/src/vid2note_core/downloaders/bbdown.py` / `ytdlp.py`

- [ ] **Step 1: bbdown.py 加 timeout**

```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)  # 30 分钟上限
```

并捕获 TimeoutExpired：

```python
import subprocess
from vid2note_core.errors import DownloadError

try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
except subprocess.TimeoutExpired as e:
    raise DownloadError(
        f"下载超时（>{1800}s）",
        code="DOWNLOAD_TIMEOUT",
        retryable=True,
        user_message="下载超时，请检查网络或更换视频",
        step="download",
    ) from e
```

- [ ] **Step 2: ytdlp.py 同样加 timeout=1800**

- [ ] **Step 3: Commit**

```bash
git add core/src/vid2note_core/downloaders/
git commit -m "fix(downloaders): subprocess 加 30 分钟超时（防止挂死泄漏 worker slot）"
```

---

## Task 6: server 加全局异常处理器 + 修 CORS（Critical 安全）

**Files:**
- Modify: `server/src/vid2note_server/main.py`

- [ ] **Step 1: 加 Vid2NoteError → HTTP 翻译**

```python
from vid2note_core.errors import Vid2NoteError
from fastapi.responses import JSONResponse


@app.exception_handler(Vid2NoteError)
async def vid2note_error_handler(request, exc: Vid2NoteError):
    status = 503 if exc.retryable else 400
    return JSONResponse(
        status_code=status,
        content={
            "error": exc.to_dict(),
            "message": exc.user_message,
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    return JSONResponse(status_code=422, content={"error": "VALIDATION_ERROR", "message": str(exc)})
```

- [ ] **Step 2: 修 CORS（Critical 安全 bug）**

```python
app.add_middleware(
    CORSMiddleware,
    # 桌面端用 file:// 加载，origin 为 null；本地开发 localhost:5173
    allow_origins=["null", "http://localhost:5173", "app://"],
    allow_credentials=False,  # 无 cookie，关闭
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

- [ ] **Step 3: 修 /health 在 degraded 时返回 503**

```python
@app.get("/api/v1/health")
async def health():
    try:
        repo = TaskRepository()
        active = repo.count_active()
        return {"status": "ok", "active_tasks": active}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "error": str(e)},
        )
```

- [ ] **Step 4: 测试 + Commit**

```python
def test_health_returns_503_when_db_down():
    # mock repo 抛错，确认返回 503
    ...

def test_vid2note_error_translated_to_503():
    # mock 端点抛 LLMRateLimited，确认 503 + retryable=True
    ...
```

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/python -m pytest server/tests/ -q 2>&1 | tail -5
git add server/src/vid2note_server/main.py server/tests/
git commit -m "fix(server): 全局异常处理器翻译Vid2NoteError+修CORS+health返回503"
```

---

## Task 7: 全量回归 + 端到端验证稳定性

- [ ] **Step 1: 全量测试**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest core/tests server/tests -q 2>&1 | tail -5`
Expected: all passed。

- [ ] **Step 2: ruff/mypy**

Run:
```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/ruff check core/src server/src
.venv/bin/mypy core/src server/src 2>&1 | tail -3
```

- [ ] **Step 3: 验证失败可见性**

手动制造失败场景：
- 用错误的 API key 跑任务 → 确认任务标记 FAILED、错误信息清晰（非"假成功"）
- kill 后端进程重启 → 确认 RUNNING 任务被恢复为 PENDING
- 模拟限流（mock）→ 确认重试 3 次后才 FAILED

---

## Self-Review

**1. Spec coverage:**
- ✅ mock ASR/LLM 兜底掩盖失败 → Task 1
- ✅ _simple_format 兜底 → Task 2
- ✅ LLM 包 RuntimeError 丢类型 + 无重试 → Task 3
- ✅ worker 无信号处理/无重试/无恢复 → Task 4
- ✅ 下载器无超时 → Task 5
- ✅ 无全局异常处理 + CORS bug + health 假绿 → Task 6
- 注：EventBus 线程安全、sync ASR on event loop 等是 Medium，可后续迭代。

**2. Placeholder:** tenacity 装饰器、错误映射、信号处理都有完整代码。glm/deepseek 的改法与 qwen 完全一致（Task 3 Step 4 说明"按同样模式改"）。

**3. Type consistency:** `LLMRateLimited("qwen")`、`LLMTimeout("qwen")` 等构造与 errors.py 定义一致。`llm_retry` 装饰器返回的 wrapper 与 chat() 签名一致。retryable 判断 `isinstance(e, Vid2NoteError) and e.retryable` 在 retry.py 和 worker.py 一致。
