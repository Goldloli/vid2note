# Knowledge Workspace Phase 0 Trusted Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复运行路径、重试、并发、恢复、媒体搬运、关闭流程和真实 E2E，使现有视频链路成为可依赖的知识库输入层。

**Architecture:** 新增一个不可变 `RuntimePaths` 作为所有数据目录的唯一来源，并通过 FastAPI app state 显式注入 Repository/Store/Worker。Worker 使用有界 asyncio task 集合并保留结构化领域错误；ArtifactStore 对大文件使用路径导入和原子移动，不再整段读入内存。

**Tech Stack:** Python 3.11、FastAPI lifespan、SQLite、asyncio、pytest、Electron、Playwright、FFmpeg。

---

## 文件结构

- Create: `core/src/vid2note_core/paths.py`
- Create: `core/tests/unit/test_paths.py`
- Modify: `core/src/vid2note_core/storage/db.py`
- Modify: `core/src/vid2note_core/storage/artifact_store.py`
- Modify: `core/src/vid2note_core/storage/upload_store.py`
- Modify: `core/src/vid2note_core/asr/local/model_manager.py`
- Modify: `core/src/vid2note_core/types.py`
- Modify: `core/src/vid2note_core/storage/task_repo.py`
- Modify: `core/src/vid2note_core/pipeline/node.py`
- Modify: `core/src/vid2note_core/pipeline/dag.py`
- Modify: `core/src/vid2note_core/pipeline/real_nodes.py`
- Modify: `core/src/vid2note_core/worker.py`
- Create: `server/src/vid2note_server/dependencies.py`
- Modify: `server/src/vid2note_server/main.py`
- Modify: `server/src/vid2note_server/api/process.py`
- Modify: `server/src/vid2note_server/api/tasks.py`
- Modify: `server/src/vid2note_server/api/upload.py`
- Modify: `server/src/vid2note_server/api/artifacts.py`
- Modify: `server/src/vid2note_server/api/config.py`
- Modify: `server/src/vid2note_server/api/models.py`
- Modify: `server/src/vid2note_server/api/logs.py`
- Modify: `server/src/vid2note_server/api/events.py`
- Modify: `desktop/src/main/index.js`
- Create: `desktop/src/main/python-service.js`
- Create: `desktop/tests/unit/python-service.test.js`
- Modify: `desktop/package.json`
- Modify: `core/src/vid2note_core/llm/factory.py`
- Modify: `core/tests/unit/llm/test_factory.py`
- Modify: `core/pyproject.toml`
- Modify: `uv.lock`
- Replace behavior in: `server/tests/integration/test_full_chain.py`
- Modify: `desktop/tests/e2e/test_url_input.spec.js`
- Create: `desktop/tests/e2e/test_local_srt_pipeline.spec.js`
- Create: `tests/golden/source_notes/manifest.yaml`
- Create: `tests/golden/source_notes/interview-noisy.srt`
- Create: `tests/golden/source_notes/lecture-terms.srt`
- Create: `tests/golden/source_notes/lecture-terms.expected.yaml`
- Create: `core/tests/golden/test_source_notes.py`
- Create: `docs/compliance/third-party-asr-audit.md`

### Task 1: 建立唯一 RuntimePaths

- [ ] **Step 1: 写路径解析失败测试**

```python
def test_runtime_paths_derive_every_directory_from_data_root(tmp_path):
    paths = RuntimePaths.from_data_root(tmp_path / "data")
    assert paths.database == tmp_path / "data" / "vault" / ".vid2note" / "state.sqlite3"
    assert paths.tasks == tmp_path / "data" / "tasks"
    assert paths.uploads == tmp_path / "data" / "uploads"
    assert paths.models == tmp_path / "data" / "models"
    assert paths.vault == tmp_path / "data" / "vault"
```

- [ ] **Step 2: 运行测试并确认因 `RuntimePaths` 不存在而失败**

Run: `uv run pytest core/tests/unit/test_paths.py -q`

Expected: FAIL with `ModuleNotFoundError: vid2note_core.paths`.

- [ ] **Step 3: 实现不可变路径对象**

```python
@dataclass(frozen=True, slots=True)
class RuntimePaths:
    data_root: Path
    database: Path
    tasks: Path
    uploads: Path
    models: Path
    vault: Path

    @classmethod
    def from_data_root(cls, root: str | Path) -> "RuntimePaths":
        data_root = Path(root).expanduser().resolve()
        data_root.mkdir(parents=True, exist_ok=True)
        return cls(
            data_root=data_root,
            database=data_root / "vault" / ".vid2note" / "state.sqlite3",
            tasks=data_root / "tasks",
            uploads=data_root / "uploads",
            models=data_root / "models",
            vault=data_root / "vault",
        )
```

- [ ] **Step 4: 将 Database/ArtifactStore/UploadStore/ModelManager 构造器改为必须接收显式路径**

保留测试可用的路径参数，但删除业务代码中所有进程相对 `data/` fallback。Server 只能从 `request.app.state.services` 获取实例。

- [ ] **Step 5: 运行路径与存储测试**

Run: `uv run pytest core/tests/unit/test_paths.py core/tests/unit/storage core/tests/unit/asr/test_model_manager.py -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add core/src/vid2note_core/paths.py core/src/vid2note_core/storage core/src/vid2note_core/asr/local/model_manager.py core/tests/unit/test_paths.py core/tests/unit/storage core/tests/unit/asr/test_model_manager.py
git commit -m "fix(runtime): centralize data root paths"
```

### Task 2: 通过 FastAPI lifespan 注入服务

- [ ] **Step 1: 写 app factory 隔离测试**

```python
def test_create_app_uses_supplied_data_root(tmp_path):
    with TestClient(create_app(tmp_path / "runtime")) as client:
        assert client.get("/api/v1/health").status_code == 200
    assert (tmp_path / "runtime" / "vault" / ".vid2note" / "state.sqlite3").exists()
    assert not Path("data/tasks").exists()
```

- [ ] **Step 2: 验证测试失败**

Run: `uv run pytest server/tests/integration/test_api.py::test_create_app_uses_supplied_data_root -q`

Expected: FAIL because `create_app` does not accept a root.

- [ ] **Step 3: 添加显式服务容器**

```python
@dataclass(slots=True)
class Services:
    paths: RuntimePaths
    database: Database
    tasks: TaskRepository
    artifacts: ArtifactStore
    uploads: UploadStore
    worker: TaskWorker

def build_services(paths: RuntimePaths) -> Services:
    database = Database(paths.database)
    tasks = TaskRepository(database)
    artifacts = ArtifactStore(paths.tasks)
    uploads = UploadStore(paths.uploads)
    worker = TaskWorker(tasks, artifacts)
    return Services(paths, database, tasks, artifacts, uploads, worker)
```

- [ ] **Step 4: 在 `create_app(data_root=None)` 的 lifespan 中启动/停止 Worker**

根目录优先级固定为显式参数 → `VID2NOTE_DATA_DIR` → 开发态仓库 `data/`，解析一次后不允许下游重新读取环境变量。

- [ ] **Step 5: 将 API handler 的裸构造改为依赖注入**

```python
def get_services(request: Request) -> Services:
    return cast(Services, request.app.state.services)
```

路由参数使用 `services: Annotated[Services, Depends(get_services)]`。

- [ ] **Step 6: 运行 Server integration tests**

Run: `uv run pytest server/tests/integration -q`

Expected: PASS and no repository-root `data/` side effects.

- [ ] **Step 7: 提交**

```bash
git add server/src/vid2note_server core/src/vid2note_core/worker.py server/tests/integration
git commit -m "fix(runtime): inject services from app lifespan"
```

### Task 3: 保留结构化错误与 retry_count

- [ ] **Step 1: 写失败测试**

```python
def test_worker_preserves_retryable_node_error(repo, worker):
    repo.create(task_id="task_123456789abc", status=TaskStatus.PENDING)
    result = NodeResult.failure(
        DownloadError("timeout", code="DOWNLOAD_TIMEOUT", retryable=True)
    )
    worker.handle_node_failure("task_123456789abc", result)
    task = repo.get_by_id("task_123456789abc")
    assert task.retry_count == 1
    assert task.status is TaskStatus.PENDING
    assert task.error_code == "DOWNLOAD_TIMEOUT"
```

- [ ] **Step 2: 验证失败原因是错误被 RuntimeError 包装或 `retry_count` 未映射**

Run: `uv run pytest core/tests/unit/test_worker.py core/tests/unit/storage/test_task_repo.py -q`

Expected: FAIL on structured error fields or retry count.

- [ ] **Step 3: 让 `NodeResult` 保存 `Vid2NoteError.to_dict()`，Worker 不再重新包装**

```python
@dataclass(slots=True)
class NodeFailure:
    code: str
    message: str
    user_message: str
    retryable: bool
    step: str | None
```

`TaskRecord.from_row()` 必须读取 `retry_count`、`error_code`、`error_retryable`；重试只在 `retryable is True and retry_count < max_retries` 时发生。

同时为既有 SQLite 增加幂等 migration：`retry_count INTEGER NOT NULL DEFAULT 0`、`error_code TEXT`、`error_retryable INTEGER NOT NULL DEFAULT 0` 和 `rerun_from_node TEXT`；迁移测试必须从旧 schema 启动并验证旧任务仍可读取。

- [ ] **Step 4: 运行错误、Repository 与 Worker 测试**

Run: `uv run pytest core/tests/unit/test_errors.py core/tests/unit/storage/test_task_repo.py core/tests/unit/test_worker.py -q`

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add core/src/vid2note_core/types.py core/src/vid2note_core/pipeline/node.py core/src/vid2note_core/storage/task_repo.py core/src/vid2note_core/worker.py core/tests/unit
git commit -m "fix(worker): preserve retryable failures"
```

### Task 4: 实现真实有界并发、from_node rerun 与 resume 校验

- [ ] **Step 1: 写三个行为测试**

```python
async def test_worker_runs_up_to_configured_concurrency(worker, repo, entered, release):
    repo.seed_pending(3)
    worker.pipeline_factory = recording_pipeline(entered, release)
    run_task = asyncio.create_task(worker.run())
    await asyncio.wait_for(entered.wait_for_count(2), timeout=1)
    assert entered.count == 2
    worker.request_stop()
    release.set()
    await run_task

async def test_rerun_passes_from_node_to_pipeline(worker, repo):
    task_id = repo.seed_completed()
    repo.rerun(task_id, from_node="transcribe")
    await worker.run_once()
    assert worker.pipeline_factory.last_start_from == "transcribe"

async def test_resume_reexecutes_node_when_declared_artifact_missing(pipeline, artifacts):
    artifacts.mark_node_completed("transcribe")
    await pipeline.run(resume=True)
    assert pipeline.nodes["transcribe"].run_count == 1
```

测试使用 barrier/event 证明两个任务同时进入执行区，不以耗时猜并发。

- [ ] **Step 2: 运行并确认三项失败**

Run: `uv run pytest core/tests/unit/test_worker.py core/tests/unit/pipeline/test_dag.py -q`

Expected: FAIL for concurrency, rerun start, and artifact completeness.

- [ ] **Step 3: 用 task set + semaphore 改造 Worker 主循环**

```python
async def run(self) -> None:
    active: set[asyncio.Task[None]] = set()
    while not self._stopping.is_set():
        active = {task for task in active if not task.done()}
        for record in self.repo.reserve_pending(self.max_concurrent - len(active)):
            active.add(asyncio.create_task(self._run_reserved(record)))
        await asyncio.sleep(self.poll_interval)
    await asyncio.gather(*active, return_exceptions=True)
```

Repository 必须用事务将 pending 原子改为 reserved/running，避免同一任务重复领取。

- [ ] **Step 4: 将 `from_node` 持久化并以 `Pipeline.run(start_from="transcribe")` 同类调用传给 Pipeline**

`rerun` 先删除该节点及下游产物，再把起点写入任务记录；Worker 成功领取后读取并传递。

- [ ] **Step 5: 让 DAG 用每个节点声明的必需产物判断是否可 resume**

仅有 node status 不足以跳过节点；任何必需文件不存在或为空时都必须重跑。

- [ ] **Step 6: 运行 Worker/Pipeline 全套测试**

Run: `uv run pytest core/tests/unit/test_worker.py core/tests/unit/pipeline -q`

Expected: PASS.

- [ ] **Step 7: 提交**

```bash
git add core/src/vid2note_core/worker.py core/src/vid2note_core/storage/task_repo.py core/src/vid2note_core/pipeline core/tests/unit/test_worker.py core/tests/unit/pipeline
git commit -m "fix(worker): add bounded concurrency and reliable resume"
```

### Task 5: 大媒体路径导入与原子落盘

- [ ] **Step 1: 写不调用 `Path.read_bytes` 的回归测试**

```python
def test_import_file_does_not_read_whole_media(tmp_path, monkeypatch):
    source = tmp_path / "large.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(AssertionError()))
    stored = ArtifactStore(tmp_path / "tasks").import_file(
        "task_123456789abc", "download", "video_file", source
    )
    assert stored.read_bytes() == b"video"
```

- [ ] **Step 2: 验证失败**

Run: `uv run pytest core/tests/unit/storage/test_artifact_store.py core/tests/unit/pipeline/test_real_nodes.py -q`

Expected: FAIL because `import_file` does not exist or nodes copy bytes.

- [ ] **Step 3: 实现同盘 `os.replace`、跨盘 `copyfileobj` 的原子导入**

```python
def import_file(self, task_id, node, name, source, *, move=False):
    destination = self.artifact_path(task_id, node, name)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    self.ensure_task_dir(task_id)
    if move:
        try:
            os.replace(source, temporary)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            shutil.copyfile(source, temporary)
            source.unlink()
    else:
        shutil.copyfile(source, temporary)
    os.replace(temporary, destination)
    return destination
```

- [ ] **Step 4: 修改 Download/ExtractAudio 节点只传 Path**

文本产物仍可使用 `write_artifact(bytes)`；视频和音频必须使用 `import_file`。

- [ ] **Step 5: 运行存储与真实节点测试**

Run: `uv run pytest core/tests/unit/storage/test_artifact_store.py core/tests/unit/pipeline/test_real_nodes.py -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add core/src/vid2note_core/storage/artifact_store.py core/src/vid2note_core/pipeline/real_nodes.py core/tests/unit/storage/test_artifact_store.py core/tests/unit/pipeline/test_real_nodes.py
git commit -m "fix(storage): stream large media artifacts"
```

### Task 6: 优雅关闭、Baidu 映射与 lock 同步

- [ ] **Step 1: 写 Electron 关闭协议与 Baidu credential 测试**

Python 测试断言 `baidu` 读取 `BAIDU_API_KEY`/`BAIDU_SECRET_KEY`；Node 测试把 child process 与 timer 注入 `PythonService`，断言先发送 `SIGTERM`，超时后才 `SIGKILL`：

```javascript
test('stop escalates only after the grace period', () => {
  const child = new FakeChild()
  const clock = new FakeClock()
  const service = new PythonService({ child, clock, graceMs: 30_000 })
  service.stop()
  assert.deepEqual(child.signals, ['SIGTERM'])
  clock.advance(30_000)
  assert.deepEqual(child.signals, ['SIGTERM', 'SIGKILL'])
})
```

- [ ] **Step 2: 实现关闭顺序**

```javascript
stop() {
  this.child.kill('SIGTERM')
  const forceKill = this.clock.setTimeout(() => this.child.kill('SIGKILL'), this.graceMs)
  this.child.once('exit', () => this.clock.clearTimeout(forceKill))
}
```

FastAPI lifespan 收到终止信号后停止领取新任务，等待 active tasks 至多 30 秒，将剩余任务标记 `interrupted`。

- [ ] **Step 3: 修正 Baidu 环境变量映射并移除对应 xfail**

- [ ] **Step 4: 运行 `uv lock`，确认 `requests` 与 `tenacity` 存在于 lock**

Run: `uv lock && rg -n 'name = "(requests|tenacity)"' uv.lock`

Expected: two dependency entries and exit 0.

- [ ] **Step 5: 在 `desktop/package.json` 增加 `"test:main": "node --test tests/unit/*.test.js"` 并运行针对性测试**

Run: `uv run pytest core/tests/unit/llm/test_factory.py core/tests/unit/test_worker.py -q && npm --prefix desktop run test:main`

Expected: Python tests and Node built-in tests both PASS.

- [ ] **Step 6: 提交**

```bash
git add desktop/src/main/index.js desktop/src/main/python-service.js desktop/tests/unit/python-service.test.js desktop/package.json core/src/vid2note_core/llm/factory.py core/tests/unit/llm/test_factory.py core/pyproject.toml uv.lock
git commit -m "fix(runtime): close services gracefully and sync dependencies"
```

### Task 7: 真实 Worker 集成、Golden Dataset 与合规审计

- [ ] **Step 1: 将 `test_full_chain.py` 改为启动真实 Worker**

测试上传固定 SRT，创建 `mock` LLM 任务，等待终态，并从 ArtifactStore 读取真实 `organize_markdown_file`；禁止测试直接写 task status 或产物。

- [ ] **Step 2: 增加桌面本地 SRT E2E**

Playwright 必须断言：任务到达 `completed`、笔记页出现固定标题、导出的 Markdown 包含 fixture 内容。所有 `try/catch` 只能捕获预期 API 错误，不能吞 `expect` 失败。

- [ ] **Step 3: 建立 Golden manifest**

```yaml
schema_version: 1
cases:
  - id: lecture-terms
    transcript: lecture-terms.srt
    expects:
      min_citation_coverage: 0.8
      forbidden_claims: []
  - id: interview-noisy
    transcript: interview-noisy.srt
    expects:
      preserve_uncertainty: true
      min_sections: 2
```

`core/tests/golden/test_source_notes.py` 读取 manifest 和人工维护的 expected YAML，计算章节数、证据链接覆盖率、禁用 claim、ASR 不确定性标记与 source id 一致性；CI 使用固定 MockLLM 输出，真实模型质量评估通过 `pytest -m golden --provider <name>` 单独运行并保存报告，不把网络波动混入普通 CI。

- [ ] **Step 4: 完成 `docs/compliance/third-party-asr-audit.md`**

文档必须列出 `bk_asr` 来源 commit、已修改文件、GPLv3 义务、是否分发、替换/隔离决策和负责人；每一项必须给出明确结论。若审计无法确认发布合规，Phase 0 状态必须标为 blocked，不得打包发布。

- [ ] **Step 5: 运行阶段验收**

Run:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy core/src server/src
npm --prefix desktop run build
npm --prefix desktop run test:e2e -- test_local_srt_pipeline.spec.js
```

Expected: all commands exit 0; Worker-driven test produces real Markdown.

- [ ] **Step 6: 更新 CodeGraph 并提交**

```bash
codegraph update
git add server/tests/integration/test_full_chain.py desktop/tests/e2e tests/golden core/tests/golden docs/compliance
git commit -m "test(e2e): prove the trusted source-note pipeline"
```
