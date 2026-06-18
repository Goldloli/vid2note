# Knowledge Workspace Phase 2 Vault And Media Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现可由 Obsidian 直接打开的 Markdown Vault、稳定来源身份、时间证据链接以及按需截图/视频片段。

**Architecture:** `vid2note_core.vault` 只处理允许 root 内的文件协议与原子单文件写入；`source` 把现有任务产物注册为不可原地改写的 raw source 和可再生成的 source note。媒体证据通过 FFmpeg 按需生成并以 source hash + 时间范围缓存，HTTP 层只校验请求并返回类型化资源。

**Tech Stack:** Python、Pydantic、PyYAML、hashlib、FFmpeg/ffprobe、FastAPI、pytest、generated TypeScript contracts。

---

## 文件结构

- Create: `core/src/vid2note_core/vault/models.py`
- Create: `core/src/vid2note_core/vault/layout.py`
- Create: `core/src/vid2note_core/vault/repository.py`
- Create: `core/src/vid2note_core/vault/log.py`
- Create: `core/src/vid2note_core/vault/watcher.py`
- Create: `core/src/vid2note_core/vault/templates/AGENTS.md`
- Create: `core/src/vid2note_core/vault/templates/index.md`
- Create: `core/src/vid2note_core/vault/templates/log.md`
- Create: `core/src/vid2note_core/source/models.py`
- Create: `core/src/vid2note_core/source/identity.py`
- Create: `core/src/vid2note_core/source/transcript.py`
- Create: `core/src/vid2note_core/source/registrar.py`
- Create: `core/src/vid2note_core/media/models.py`
- Create: `core/src/vid2note_core/media/citation.py`
- Create: `core/src/vid2note_core/media/ffmpeg.py`
- Create: `core/tests/unit/vault/test_layout.py`
- Create: `core/tests/unit/vault/test_repository.py`
- Create: `core/tests/unit/vault/test_log.py`
- Create: `core/tests/unit/vault/test_watcher.py`
- Create: `core/tests/unit/source/test_identity.py`
- Create: `core/tests/unit/source/test_transcript.py`
- Create: `core/tests/unit/source/test_registrar.py`
- Create: `core/tests/unit/media/test_citation.py`
- Create: `core/tests/unit/media/test_ffmpeg.py`
- Create: `server/src/vid2note_server/schemas/vault.py`
- Create: `server/src/vid2note_server/schemas/sources.py`
- Create: `server/src/vid2note_server/schemas/media.py`
- Create: `server/src/vid2note_server/api/vault.py`
- Create: `server/src/vid2note_server/api/sources.py`
- Create: `server/src/vid2note_server/api/media.py`
- Create: `server/tests/integration/test_vault_api.py`
- Create: `server/tests/integration/test_source_ingest.py`
- Create: `server/tests/integration/test_media_api.py`
- Modify: `server/src/vid2note_server/main.py`
- Modify: `core/src/vid2note_core/pipeline/real_nodes.py`

### Task 1: 初始化并校验 Vault 磁盘协议

- [ ] **Step 1: 写 Vault layout 测试**

```python
def test_initialize_creates_human_readable_vault(tmp_path):
    layout = VaultLayout.initialize(tmp_path / "vault")
    assert layout.agents.read_text().startswith("# vid2note Wiki Schema")
    assert layout.index.read_text().startswith("# Index")
    assert layout.log.read_text().startswith("# Log")
    assert layout.wiki.joinpath("concepts").is_dir()
    assert layout.private.joinpath("cache", "clips").is_dir()
```

- [ ] **Step 2: 运行并确认模块不存在**

Run: `uv run pytest core/tests/unit/vault/test_layout.py -q`

Expected: FAIL with missing module.

- [ ] **Step 3: 实现 `VaultLayout`**

```python
@dataclass(frozen=True, slots=True)
class VaultLayout:
    root: Path
    raw: Path
    sources: Path
    wiki: Path
    assets: Path
    private: Path
    agents: Path
    index: Path
    log: Path
```

`initialize()` 只创建缺失目录/模板，绝不覆盖用户已有 `AGENTS.md`、`index.md` 或 `log.md`。

- [ ] **Step 4: 模板写入规格 §7–8 的最小规则**

AGENTS 模板必须说明 index-first、允许页面类型、frontmatter 字段、时间证据格式、ChangeSet 写入规则与禁止向量索引。

- [ ] **Step 5: 运行 layout tests**

Run: `uv run pytest core/tests/unit/vault/test_layout.py -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add core/src/vid2note_core/vault core/tests/unit/vault/test_layout.py
git commit -m "feat(vault): initialize the markdown vault layout"
```

### Task 2: 安全页面 Repository 与 human-edit 日志

- [ ] **Step 1: 写路径逃逸、symlink 与 base hash 测试**

```python
def test_repository_rejects_escape(repository):
    with pytest.raises(VaultPathError):
        repository.read_page("../outside.md")

def test_repository_rejects_symlink_outside_root(repository, tmp_path):
    (repository.root / "escape.md").symlink_to(tmp_path / "outside.md")
    with pytest.raises(VaultPathError):
        repository.read_page("escape.md")

def test_human_update_requires_matching_base_hash(repository, page):
    with pytest.raises(VaultConflict):
        repository.update_human(page.path, "changed", base_hash="stale")

def test_human_update_appends_log_entry(repository, page):
    repository.update_human(page.path, "changed", base_hash=page.content_hash)
    assert "human-edit" in repository.layout.log.read_text()
```

- [ ] **Step 2: 定义页面模型**

```python
class VaultPage(BaseModel):
    path: str
    content: str
    content_hash: str
    modified_at: datetime
    frontmatter: dict[str, JsonValue] | None = None

class HumanPageUpdate(BaseModel):
    content: str
    base_hash: str
```

- [ ] **Step 3: 实现 canonical path resolver**

所有相对路径先拒绝绝对路径与 `..`，再 `resolve(strict=False)`，最后用 `is_relative_to(layout.root.resolve())` 校验。禁止跟随指向 root 外部的 symlink。

- [ ] **Step 4: 实现原子 human update**

先比较 SHA-256 base hash，再写同目录临时文件、`fsync`、`os.replace`。成功后向 `log.md` 追加 `human-edit`，日志内容包含 path、before/after hash，不包含完整正文。

- [ ] **Step 5: 运行 Repository 测试**

Run: `uv run pytest core/tests/unit/vault/test_repository.py core/tests/unit/vault/test_log.py -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add core/src/vid2note_core/vault/models.py core/src/vid2note_core/vault/repository.py core/src/vid2note_core/vault/log.py core/tests/unit/vault
git commit -m "feat(vault): add safe page reads and human edits"
```

### Task 3: 来源身份、source.yaml 与 transcript.md

- [ ] **Step 1: 写稳定身份测试**

```python
def test_same_content_reuses_source_id(tmp_path):
    identities = SourceIdentityRepository(tmp_path / "vault")
    first = identities.get_or_create("https://example.com/watch?v=1", b"same", date(2026, 6, 18))
    second = identities.get_or_create("https://example.com/watch?v=1&utm_source=x", b"same", date(2026, 6, 19))
    assert first.source_id == second.source_id
```

- [ ] **Step 2: 定义 SourceRecord/TimelineSegment**

```python
class TimelineSegment(BaseModel):
    segment_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    speaker: str | None = None

class SourceRecord(BaseModel):
    source_id: str
    canonical_url: str | None
    content_sha256: str
    title: str
    duration_ms: int
    imported_at: datetime
    original_available: bool
    original_relative_path: str | None
```

- [ ] **Step 3: 实现 URL 规范化与 source id**

移除 tracking query，保留影响内容身份的站点 id；本地文件用内容 hash。`source_id` 格式为 `src_YYYYMMDD_<8hex>`，重复内容查询现有 `raw/*/source.yaml` 后复用首次 id。

- [ ] **Step 4: 把 SRT 标准化为稳定 segments 与 block ids**

```markdown
## 00:12:41–00:13:28

企业内部 AI 落地必须是一号位工程。 ^seg-000142
```

segment id 由 source revision 内的顺序、start/end/text hash 生成；同一 SRT 重建必须一致。

- [ ] **Step 5: 运行 source tests**

Run: `uv run pytest core/tests/unit/source -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add core/src/vid2note_core/source core/tests/unit/source
git commit -m "feat(vault): add stable source identity and transcripts"
```

### Task 4: 将现有任务产物注册到 Vault

- [ ] **Step 1: 写 registrar 原子性测试**

```python
def test_register_source_writes_raw_and_source_note(tmp_path, completed_task):
    record = registrar.register(completed_task)
    assert (layout.raw / record.source_id / "source.yaml").exists()
    assert (layout.raw / record.source_id / "transcript.srt").exists()
    assert list(layout.sources.glob(f"{record.source_id}--*.md"))
```

- [ ] **Step 2: 实现 `SourceRegistrar.register`**

输入只接受已完成任务及 artifact Paths；先在 `.vid2note/staging/<source_id>` 生成全部文件，校验后移动到 `raw/` 与 `sources/`。重复 source 默认返回已有 record，不复制 raw。

- [ ] **Step 3: 在 Pipeline 添加 `register_source` 节点**

该节点位于 source note 之后、Wiki proposal 之前；Phase 2 只注册，不创建 Wiki ChangeSet。现有 organize Markdown 迁为 source note，并增加 source frontmatter 与时间证据。

- [ ] **Step 4: 加入来源笔记时间证据质量测试**

Golden fixture 的关键章节必须包含至少一个 `vid2note://source/src_20260618_a1b2c3d4?start=761000&end=808000` 同格式链接；模型补充推断必须写入“综合/推断”区而不能伪装为视频事实。

- [ ] **Step 5: 运行 Pipeline 与 registrar tests**

Run: `uv run pytest core/tests/unit/source core/tests/unit/pipeline server/tests/integration/test_source_ingest.py -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add core/src/vid2note_core/source core/src/vid2note_core/pipeline core/tests/unit/source core/tests/unit/pipeline server/tests/integration/test_source_ingest.py
git commit -m "feat(vault): register pipeline outputs as sources"
```

### Task 5: 实现 Vault/Source API

- [ ] **Step 1: 写 API 集成测试**

```python
def test_vault_tree_read_search_and_human_update(client, vault_fixture):
    assert client.get("/api/v1/vault/tree").status_code == 200
    result = client.get("/api/v1/vault/search", params={"q": "POC"}).json()
    assert result[0]["path"] == "wiki/concepts/poc-trap.md"
    page = client.get("/api/v1/vault/page", params={"path": result[0]["path"]}).json()
    response = client.put(
        "/api/v1/vault/page",
        params={"path": page["path"]},
        json={"content": page["content"] + "\nHuman note.\n", "base_hash": page["content_hash"]},
    )
    assert response.status_code == 200

def test_vault_page_rejects_stale_base_hash(client, vault_fixture):
    response = client.put(
        "/api/v1/vault/page",
        params={"path": "index.md"},
        json={"content": "changed", "base_hash": "stale"},
    )
    assert response.status_code == 409

def test_sources_ingest_returns_existing_source_for_duplicate(client, source_payload):
    first = client.post("/api/v1/sources/ingest", json=source_payload).json()
    second = client.post("/api/v1/sources/ingest", json=source_payload).json()
    assert second["source_id"] == first["source_id"]
```

- [ ] **Step 2: 注册类型化 endpoints**

```text
GET  /api/v1/vault/tree
GET  /api/v1/vault/page?path={relative_path}
PUT  /api/v1/vault/page?path={relative_path}
GET  /api/v1/vault/search?q={plain_text}
POST /api/v1/sources/ingest
GET  /api/v1/sources/{source_id}
```

Search 只扫描允许 Markdown 文件的文件名、frontmatter/title 与普通文本；限制结果数和最大读取字节，不构建 embedding。

- [ ] **Step 3: 将 Vault services 加入 `Services` 容器**

API 不直接实例化 Layout/Repository/Registrar。

- [ ] **Step 4: 重新生成 OpenAPI/TypeScript**

Run: `npm --prefix desktop run contracts:export && npm --prefix desktop run contracts:generate`

Expected: generated schema contains `VaultPage`, `SourceRecord`, `HumanPageUpdate`.

- [ ] **Step 5: 运行 API tests**

Run: `uv run pytest server/tests/integration/test_vault_api.py server/tests/integration/test_source_ingest.py -q`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add server/src/vid2note_server desktop/openapi.json desktop/src/renderer/api/generated/schema.ts server/tests/integration
git commit -m "feat(vault): expose typed vault and source APIs"
```

### Task 6: 按需生成截图和视频片段

- [ ] **Step 1: 写时间边界和缓存测试**

```python
def test_media_reference_rejects_end_beyond_duration(media_service, source):
    with pytest.raises(MediaRangeError):
        media_service.clip(source.source_id, start_ms=0, end_ms=source.duration_ms + 1)

def test_frame_cache_key_includes_source_hash_and_timestamp(cache_key):
    assert cache_key("abc", "frame", 1000, None) != cache_key("abc", "frame", 2000, None)

def test_clip_generation_adds_buffer_and_clamps_to_media_bounds(media_service, short_source):
    reference = media_service.clip(short_source.source_id, start_ms=500, end_ms=9500, buffer_ms=1500)
    assert reference.rendered_start_ms == 0
    assert reference.rendered_end_ms == short_source.duration_ms
```

- [ ] **Step 2: 定义媒体模型**

```python
class MediaReference(BaseModel):
    source_id: str
    kind: Literal["frame", "clip", "audio"]
    start_ms: int
    end_ms: int | None = None
    rendered_start_ms: int
    rendered_end_ms: int | None = None
    asset_path: str
    cached: bool
    playable: bool
```

- [ ] **Step 3: 实现受控 FFmpeg runner**

命令参数使用 list，不使用 shell；输入必须来自 SourceRecord 的 original path；输出必须位于 `.vid2note/cache/frames|clips`。clip 默认前后各 1500ms buffer，最终范围 clamp 到 0..duration。

- [ ] **Step 4: 实现 cache key 与 promote-to-assets**

缓存键为 SHA-256(`content_sha256|kind|start|end|buffer|codec-version`)；正式 Wiki 引用图片时复制到 `assets/<source_id>/` 并返回相对路径。

- [ ] **Step 5: 暴露 `/media/frame` 和 `/media/clip`**

原视频不存在时返回 typed `SOURCE_MEDIA_UNAVAILABLE`，并在 response details 提供 transcript path 与 canonical URL，不伪装 playable。

- [ ] **Step 6: 运行 media tests**

Run: `uv run pytest core/tests/unit/media server/tests/integration/test_media_api.py -q`

Expected: PASS; repeated request returns `cached=true`.

- [ ] **Step 7: 提交**

```bash
git add core/src/vid2note_core/media core/tests/unit/media server/src/vid2note_server/api/media.py server/src/vid2note_server/schemas/media.py server/tests/integration/test_media_api.py
git commit -m "feat(media): generate evidence frames and clips on demand"
```

### Task 7: 外部编辑监听与 Phase 2 验收

- [ ] **Step 1: 写 watcher 去抖与外部编辑测试**

同一文件保存触发的多次事件只追加一次 `external-edit`；`.vid2note/cache` 与应用自身临时文件不触发。

- [ ] **Step 2: 实现轮询式轻量 watcher**

每秒比较 Markdown 文件 `(mtime_ns, size, sha256)` 快照；仅用户可见 Markdown 纳入监听。Phase 2 规模下不增加平台文件监听依赖，后续只有在测得性能瓶颈时替换。

- [ ] **Step 3: 在 lifespan 启停 watcher**

退出时先停止 watcher，再停止 Worker；内部写入使用 operation id 抑制重复 external-edit 日志。

- [ ] **Step 4: 验证数据库可删除性**

集成测试创建 source、停止服务、删除 `.vid2note/state.sqlite3`、重启服务，断言 source note、index/log/raw 仍可读，并能重建 source 列表。

- [ ] **Step 5: 运行阶段验收**

Run:

```bash
uv run pytest core/tests/unit/vault core/tests/unit/source core/tests/unit/media -q
uv run pytest server/tests/integration/test_vault_api.py server/tests/integration/test_source_ingest.py server/tests/integration/test_media_api.py -q
uv run ruff check .
uv run mypy core/src server/src
npm --prefix desktop run contracts:check
```

Expected: all commands exit 0; media seek error fixture is at most 2000ms.

- [ ] **Step 6: 更新 CodeGraph 并提交**

```bash
codegraph update
git add core/src/vid2note_core/vault server/src/vid2note_server/main.py core/tests/unit/vault server/tests/integration desktop/openapi.json desktop/src/renderer/api/generated/schema.ts
git commit -m "feat(vault): track external edits and rebuild from markdown"
```
