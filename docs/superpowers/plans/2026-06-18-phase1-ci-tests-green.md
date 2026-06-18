# Phase 1: CI / 测试套件恢复绿灯 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `pytest -x`、`ruff check`、`ruff format --check`、`mypy` 四项全部恢复绿灯，并为新增的 `bk_adapter` / `_resolve_llm_creds` 补齐单元测试。

**Architecture:** 不改动业务逻辑，只做三件事：(1) 把 vendored 的 `bk_asr/` 第三方代码排除出 lint/type 检查范围（它不是我们的代码，无法也不应"修好"它的 96 个 ruff 错误）；(2) 修正过期的 `test_asr_factory.py` 断言以匹配工厂改返回 `BkAsrAdapter` 的事实；(3) 为新代码补测试。所有改动都在 `core/`、`pyproject.toml`、测试目录内，不触碰 server/desktop。

**Tech Stack:** pytest、pytest-asyncio、ruff、mypy、Python 3.11。

**前提：** 项目根目录的 `.venv` 已安装全部依赖（`.venv/bin/python` 可用），工作目录为 `/Users/gejiawei/Desktop/ai_code/vid2note`。

---

## 文件结构（改动清单）

- Modify: `pyproject.toml` — 增加 ruff `exclude` / `per-file-ignores`、mypy `exclude`，让 vendored 目录豁免
- Modify: `core/tests/unit/asr/test_asr_factory.py` — 修正断言（从 `AsrToolsBLLM` → `BkAsrAdapter`），并增加 provider 配置测试
- Create: `core/tests/unit/asr/test_bk_adapter.py` — `BkAsrAdapter` 单元测试（mock bk_asr 后端）
- Create: `core/tests/unit/test_worker_creds.py` — `_resolve_llm_creds` 单元测试（含 baidu↔BAICHUAN 问题验证）
- Modify: `core/src/vid2note_core/asr/cloud/asrtools.py` — 删除这个 338 行死代码模块（已被 `bk_adapter.py` 取代）

---

## Task 1: 修正 test_asr_factory.py 断言失败（Critical）

工厂已改返回 `BkAsrAdapter`，但测试仍断言 `AsrToolsBLLM`。

**Files:**
- Modify: `core/tests/unit/asr/test_asr_factory.py`

- [ ] **Step 1: 查看当前失败测试**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest core/tests/unit/asr/test_asr_factory.py -v`
Expected: `test_create_asrtools` FAIL，断言 `isinstance(asr, AsrToolsBLLM)` 失败，因为实际返回 `BkAsrAdapter`。

- [ ] **Step 2: 重写测试文件**

```python
"""测试 ASR 工厂"""

import pytest
from vid2note_core.asr.cloud.bk_adapter import BkAsrAdapter
from vid2note_core.asr.factory import ASRFactory


def test_create_asrtools_b():
    """asrtools-b 现在由 BkAsrAdapter 实现（基于 bk_asr 云端接口）。"""
    asr = ASRFactory.create("asrtools-b", {})
    assert isinstance(asr, BkAsrAdapter)


def test_create_asrtools_b_with_backend_config():
    """config['backend'] 应透传给 BkAsrAdapter。"""
    asr = ASRFactory.create("asrtools-b", {"backend": "kuaishou"})
    assert isinstance(asr, BkAsrAdapter)
    assert asr.backend_name == "kuaishou"


def test_unsupported_provider():
    with pytest.raises(ValueError):
        ASRFactory.create("unknown", {})


def test_available_providers():
    providers = ASRFactory.get_available_providers()
    assert "asrtools-b" in providers
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest core/tests/unit/asr/test_asr_factory.py -v`
Expected: 4 passed。

- [ ] **Step 4: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add core/tests/unit/asr/test_asr_factory.py
git commit -m "fix(test): asr 工厂断言改为 BkAsrAdapter（asrtools-b 已迁移到 bk_asr）"
```

---

## Task 2: 排除 vendored bk_asr 目录的 ruff/mypy 检查（Critical）

`core/src/vid2note_core/asr/bk_asr/` 是从 AsrTools 项目整体复制的第三方代码，有 96 个 ruff 错误和 31 个 mypy 错误。我们不应"修复"它（维护负担、且会偏离上游），应排除检查范围。

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 查看当前 lint 错误规模**

Run:
```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/ruff check core/src server/src 2>&1 | tail -3
.venv/bin/ruff format --check core/src server/src 2>&1 | tail -3
.venv/bin/mypy core/src server/src 2>&1 | tail -3
```
Expected: ruff ~96 errors、format 8 files、mypy ~31 errors，几乎全在 `asr/bk_asr/`。

- [ ] **Step 2: 修改 pyproject.toml 增加 exclude**

在 `[tool.ruff]` 段增加 `extend-exclude`，在 `[tool.mypy]` 段增加 `exclude`。定位到现有这两段（行号约 24-30 和 38-46），改成：

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
# bk_asr/ 是 vendored 第三方代码（github.com/WEIFENG2333/AsrTools），
# 不纳入我们的代码质量门禁，避免上游更新时产生维护负担。
extend-exclude = ["core/src/vid2note_core/asr/bk_asr"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
# errors.py 的领域异常类采用 DownloadXxx/ASRXxx 命名约定（领域可读性优先于 Error 后缀）
"core/src/vid2note_core/errors.py" = ["N818"]
# types.py 的枚举有意继承 (str, Enum) 以保证 JSON 序列化兼容
"core/src/vid2note_core/types.py" = ["UP042"]
# vendored bk_asr：全部豁免（已在 extend-exclude，这里是双保险）
"core/src/vid2note_core/asr/bk_asr/*" = ["ALL"]

[tool.ruff.format]
# 同样排除 vendored 目录的格式化检查
exclude = ["core/src/vid2note_core/asr/bk_asr"]

[tool.mypy]
python_version = "3.11"
# 渐进式类型检查：不强制 strict（既有代码大量未注解），
# 保留真正的类型错误检测，逐步收紧。
ignore_missing_imports = true
check_untyped_defs = false
disallow_untyped_defs = false
warn_return_any = false
warn_unused_ignores = true
# vendored bk_asr 不参与类型检查
exclude = ["core/src/vid2note_core/asr/bk_asr/"]
```

- [ ] **Step 3: 验证 ruff 通过**

Run:
```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/ruff check core/src server/src 2>&1 | tail -3
.venv/bin/ruff format --check core/src server/src 2>&1 | tail -3
```
Expected: `All checks passed!` / `8 files would be reformat` 消失 → `X files already formatted`（或无输出）。若 bk_asr 外的文件仍有错误，逐一修复（应该是 0 个或个位数）。

- [ ] **Step 4: 验证 mypy 通过**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/mypy core/src server/src 2>&1 | tail -5`
Expected: `Success: no issues found`（或仅剩 bk_asr 外的少量已知问题，逐条修）。

- [ ] **Step 5: 验证 bk_asr 仍可正常导入**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -c "from vid2note_core.asr.bk_asr import BcutASR; print('bk_asr import OK')"`
Expected: `bk_asr import OK`（确认 exclude 只影响检查，不影响运行时导入）。

- [ ] **Step 6: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add pyproject.toml
git commit -m "build: vendored bk_asr 排除 ruff/mypy 检查（第三方代码不纳入质量门禁）"
```

---

## Task 3: 删除死代码 asrtools.py（High）

`asr/cloud/asrtools.py`（338 行）是占位实现，工厂已不再注册它，仅被刚改好的测试间接引用（Task 1 已移除引用）。删除它消除混淆。

**Files:**
- Delete: `core/src/vid2note_core/asr/cloud/asrtools.py`

- [ ] **Step 1: 确认无生产引用**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && grep -rn "asrtools.py\|AsrToolsBLLM\|from vid2note_core.asr.cloud.asrtools" core/src server/src --include="*.py" | grep -v bk_`
Expected: 无输出（Task 1 改完后测试不再引用；若有残留引用先修）。

- [ ] **Step 2: 删除文件**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
rm core/src/vid2note_core/asr/cloud/asrtools.py
```

- [ ] **Step 3: 删除其旧测试（若存在）**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
rm -f core/tests/unit/asr/test_asrtools.py
```

- [ ] **Step 4: 验证全量测试仍通过**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest core/tests -q 2>&1 | tail -5`
Expected: all passed（无 ImportError、无引用 asrtools 的残留测试失败）。

- [ ] **Step 5: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add -A core/src/vid2note_core/asr/cloud/asrtools.py core/tests/
git commit -m "refactor(asr): 删除占位的 AsrToolsBLLM（已被 bk_adapter 取代）"
```

---

## Task 4: 为 BkAsrAdapter 补单元测试（High）

`bk_adapter.py` 是当前默认 ASR provider，但零测试。用 mock 验证：后端选择、segment 映射、文件不存在错误、不可识别后缀的重命名兜底。

**Files:**
- Create: `core/tests/unit/asr/test_bk_adapter.py`

- [ ] **Step 1: 写测试文件**

```python
"""测试 BkAsrAdapter（基于 bk_asr 的云端 ASR 适配器）。

用 monkeypatch 替换 bk_asr 的真实 HTTP 调用，验证适配层逻辑。
"""

from pathlib import Path

import pytest

from vid2note_core.asr.cloud.bk_adapter import BkAsrAdapter
from vid2note_core.errors import ASRError


class _FakeSegment:
    """模拟 bk_asr 的 segment 对象。"""

    def __init__(self, text: str, start_time: int, end_time: int):
        self.text = text
        self.start_time = start_time
        self.end_time = end_time


class _FakeASRData:
    """模拟 bk_asr 的 run() 返回对象。"""

    def __init__(self, segments):
        self.segments = segments


class _FakeBackend:
    """模拟 BcutASR/JianYingASR/KuaiShouASR 类。"""

    def __init__(self, audio_path, use_cache=False):
        self.audio_path = audio_path
        self.use_cache = use_cache

    def run(self):
        return _FakeASRData(
            segments=[
                _FakeSegment("你好世界", 0, 1500),
                _FakeSegment("测试识别", 1500, 3000),
                _FakeSegment("", 3000, 3500),  # 空文本应被跳过
            ]
        )


def test_unsupported_backend_raises():
    with pytest.raises(ValueError, match="不支持的 bk_asr 后端"):
        BkAsrAdapter(backend="invalid")


def test_default_backend_is_bcut():
    asr = BkAsrAdapter()
    assert asr.backend_name == "bcut"
    assert asr.is_available() is True


def test_transcribe_maps_segments(tmp_path, monkeypatch):
    """验证 bk_asr 返回的 segments 正确映射为 ASRResult。"""
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake audio")

    monkeypatch.setattr(
        "vid2note_core.asr.cloud.bk_adapter.BcutASR", _FakeBackend
    )

    asr = BkAsrAdapter(backend="bcut")
    result = asr.transcribe(audio, {"language": "zh"})

    assert result.language == "zh"
    assert len(result.segments) == 2  # 空文本 segment 被跳过
    assert result.segments[0].text == "你好世界"
    assert result.segments[0].start_ms == 0
    assert result.segments[1].start_ms == 1500
    assert "你好世界测试识别" == result.text_full
    assert result.duration_ms == 3000


def test_transcribe_missing_file_raises(tmp_path):
    asr = BkAsrAdapter(backend="bcut")
    with pytest.raises(ASRError, match="音频文件不存在"):
        asr.transcribe(tmp_path / "nope.wav", {"language": "zh"})


def test_transcribe_backend_failure_wraps_asr_error(tmp_path, monkeypatch):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"fake")

    class _CrashingBackend(_FakeBackend):
        def run(self):
            raise ConnectionError("upstream down")

    monkeypatch.setattr(
        "vid2note_core.asr.cloud.bk_adapter.BcutASR", _CrashingBackend
    )

    asr = BkAsrAdapter(backend="bcut")
    with pytest.raises(ASRError, match="bk_asr .* 识别失败"):
        asr.transcribe(audio, {"language": "zh"})


def test_ensure_readable_renames_bad_suffix(tmp_path):
    """后缀不在白名单时应重命名为 .wav。"""
    bad = tmp_path / "audio.dat"
    bad.write_bytes(b"fake")
    renamed = BkAsrAdapter._ensure_readable(bad)
    assert renamed.suffix == ".wav"
    assert renamed.exists()
    assert not bad.exists()
```

- [ ] **Step 2: 运行测试验证通过**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest core/tests/unit/asr/test_bk_adapter.py -v`
Expected: 6 passed。

- [ ] **Step 3: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add core/tests/unit/asr/test_bk_adapter.py
git commit -m "test(asr): 为 BkAsrAdapter 补单元测试（segment 映射/错误处理/后缀兜底）"
```

---

## Task 5: 为 _resolve_llm_creds 补单元测试（High）

`worker.py:_resolve_llm_creds` 的 provider→env 映射未经测试，且 `baidu→BAICHUAN_API_KEY` 疑似 bug。用测试固化当前行为（并在注释中标记待修）。

**Files:**
- Create: `core/tests/unit/test_worker_creds.py`

- [ ] **Step 1: 写测试文件**

```python
"""测试 worker._resolve_llm_creds（provider→API key/model 解析）。"""

import pytest

from vid2note_core.worker import _resolve_llm_creds


def test_qwen_reads_dashscope_key(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-123")
    monkeypatch.delenv("QWEN_MODEL", raising=False)
    key, model = _resolve_llm_creds("qwen")
    assert key == "sk-test-123"
    assert model == "qwen-turbo"


def test_model_overridable_via_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-x")
    monkeypatch.setenv("QWEN_MODEL", "qwen-max")
    _, model = _resolve_llm_creds("qwen")
    assert model == "qwen-max"


def test_glm_reads_zhipu_key(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "zhipu-key")
    monkeypatch.delenv("GLM_MODEL", raising=False)
    key, model = _resolve_llm_creds("glm")
    assert key == "zhipu-key"
    assert model == "glm-4-flash"


def test_missing_key_returns_empty_string(monkeypatch):
    """环境变量未设置时应返回空串（而非抛错，交给 LLM 构造时失败）。"""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    key, _ = _resolve_llm_creds("qwen")
    assert key == ""


def test_unknown_provider_falls_back(monkeypatch):
    """未知 provider 用 {PROVIDER}_API_KEY 兜底。"""
    monkeypatch.setenv("FOO_API_KEY", "foo-key")
    key, _ = _resolve_llm_creds("foo")
    assert key == "foo-key"


@pytest.mark.xfail(reason="已知问题：baidu 错误映射到 BAICHUAN_API_KEY，Phase 4 稳定性阶段修复")
def test_baidu_mapping_bug():
    """baidu 应读 BAIDU_API_KEY 而非 BAICHUAN_API_KEY。当前是 bug。"""
    import os
    os.environ.pop("BAICHUAN_API_KEY", None)
    os.environ["BAIDU_API_KEY"] = "baidu-key"
    key, _ = _resolve_llm_creds("baidu")
    assert key == "baidu-key"
```

- [ ] **Step 2: 运行测试验证通过**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest core/tests/unit/test_worker_creds.py -v`
Expected: 5 passed, 1 xfailed（baidu bug 标记为已知）。

- [ ] **Step 3: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add core/tests/unit/test_worker_creds.py
git commit -m "test(worker): 为 _resolve_llm_creds 补测试（含 baidu 映射 bug 标记 xfail）"
```

---

## Task 6: 全量回归 + 验证 CI 四项全绿

**Files:** 无（验证步骤）

- [ ] **Step 1: 全量 pytest**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest core/tests server/tests -q 2>&1 | tail -5`
Expected: all passed（约 172 passed，含新增 12 个测试），无 failed。

- [ ] **Step 2: ruff 全绿**

Run:
```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/ruff check core/src server/src && echo "CHECK OK"
.venv/bin/ruff format --check core/src server/src && echo "FORMAT OK"
```
Expected: 两个都 OK。

- [ ] **Step 3: mypy 全绿**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/mypy core/src server/src 2>&1 | tail -3`
Expected: `Success: no issues found`。

- [ ] **Step 4: 提交并推送（可选，需用户确认）**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git log --oneline -6
```
确认 6 个 commit 都在本地。提示用户是否 push 触发 CI 验证。

---

## Self-Review

**1. Spec coverage（对应 review 里的 Critical/High 测试问题）:**
- ✅ `test_asr_factory` 失败 → Task 1
- ✅ bk_asr 96 ruff/mypy 错误 → Task 2（排除）
- ✅ `asrtools.py` 死代码 → Task 3
- ✅ bk_adapter 零测试 → Task 4
- ✅ `_resolve_llm_creds` 未测试 → Task 5
- ✅ 四项 CI 门禁全绿 → Task 6
- 注：real_nodes 全 mock、integration test 不跑 pipeline 是 Medium，留给后续阶段。

**2. Placeholder scan:** 无 TBD/TODO/省略代码块，每步都有完整代码和确切命令。

**3. Type consistency:** `BkAsrAdapter` 的属性名（`backend_name`、`is_available()`）在 Task 1/Task 4 测试中与 `bk_adapter.py:34,109` 一致。`_resolve_llm_creds` 返回 `tuple[str, str]` 在 Task 5 测试中一致。
