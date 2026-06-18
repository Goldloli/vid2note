# Knowledge Workspace Phase 3 Wiki Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 index-first Wiki 编译、结构化 ChangeSet、审批/回滚、矛盾保留、原子多文件写入与三档自治策略。

**Architecture:** Compiler 只产生 ChangeSet，不直接写正式 Wiki；Validator 检查 schema、frontmatter、双链、证据与 base hash；Applier 是唯一 Agent/Compiler 写入者，并将页面、`index.md`、`log.md` 和快照作为一个逻辑事务处理。模型调用通过现有 LLM adapter 注入，场景测试使用 deterministic fake，不依赖付费 API。

**Tech Stack:** Python、Pydantic、PyYAML、difflib、SQLite metadata、FastAPI、pytest、Vue generated contracts。

---

## 文件结构

- Create: `core/src/vid2note_core/wiki/models.py`
- Create: `core/src/vid2note_core/wiki/store.py`
- Create: `core/src/vid2note_core/wiki/index.py`
- Create: `core/src/vid2note_core/wiki/retrieval.py`
- Create: `core/src/vid2note_core/wiki/compiler.py`
- Create: `core/src/vid2note_core/wiki/validator.py`
- Create: `core/src/vid2note_core/wiki/applier.py`
- Create: `core/src/vid2note_core/wiki/policy.py`
- Create: `core/src/vid2note_core/wiki/lint.py`
- Create: `core/src/vid2note_core/prompts/wiki_ingest.txt`
- Create: `core/src/vid2note_core/prompts/wiki_query_writeback.txt`
- Create: `core/tests/unit/wiki/test_models.py`
- Create: `core/tests/unit/wiki/test_store.py`
- Create: `core/tests/unit/wiki/test_index.py`
- Create: `core/tests/unit/wiki/test_retrieval.py`
- Create: `core/tests/unit/wiki/test_compiler.py`
- Create: `core/tests/unit/wiki/test_validator.py`
- Create: `core/tests/unit/wiki/test_applier.py`
- Create: `core/tests/unit/wiki/test_policy.py`
- Create: `core/tests/unit/wiki/test_lint.py`
- Create: `core/tests/scenarios/wiki/test_compiler_scenarios.py`
- Create: `core/tests/scenarios/wiki/fixtures/01-create-concept.yaml`
- Create: `core/tests/scenarios/wiki/fixtures/02-enhance-existing.yaml`
- Create: `core/tests/scenarios/wiki/fixtures/03-ignore-duplicate.yaml`
- Create: `core/tests/scenarios/wiki/fixtures/04-correct-claim.yaml`
- Create: `core/tests/scenarios/wiki/fixtures/05-preserve-contradiction.yaml`
- Create: `core/tests/scenarios/wiki/fixtures/06-reject-stale-base-hash.yaml`
- Create: `server/src/vid2note_server/schemas/changesets.py`
- Create: `server/src/vid2note_server/api/changesets.py`
- Create: `server/src/vid2note_server/api/wiki.py`
- Create: `server/tests/integration/test_changesets_api.py`
- Create: `server/tests/integration/test_wiki_ingest.py`
- Modify: `core/src/vid2note_core/pipeline/real_nodes.py`
- Modify: `server/src/vid2note_server/main.py`

### Task 1: 定义 ChangeSet 与持久化格式

- [ ] **Step 1: 写 JSON round-trip 与状态机测试**

```python
def test_changeset_round_trip_preserves_operations_and_citations(tmp_path, changeset):
    store = ChangeSetStore(tmp_path)
    store.save_pending(changeset)
    assert store.get(changeset.id) == changeset

def test_changeset_cannot_apply_after_rejection(tmp_path, changeset):
    store = ChangeSetStore(tmp_path)
    store.save_pending(changeset)
    store.reject(changeset.id, reason="not relevant")
    with pytest.raises(InvalidChangeSetTransition):
        store.mark_applied(changeset.id)

def test_changeset_requires_at_least_one_operation(changeset_payload):
    changeset_payload["operations"] = []
    with pytest.raises(ValidationError):
        ChangeSet.model_validate(changeset_payload)
```

- [ ] **Step 2: 定义不可变领域模型**

```python
class Citation(BaseModel):
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

class Contradiction(BaseModel):
    topic: str
    claim_a: str
    claim_b: str
    citations_a: list[Citation]
    citations_b: list[Citation]
    requires_approval: bool = True

class ValidationIssue(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    operation_index: int | None
    path: str | None
    message: str

class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue]

class ChangeOperation(BaseModel):
    page_id: str
    path: str
    base_hash: str | None
    action: Literal["create", "update", "rename"]
    before: str | None
    after: str
    rationale: str
    citations: list[Citation]

class ChangeSet(BaseModel):
    id: str
    created_at: datetime
    source_ids: list[str]
    base_revision: str
    agent_runtime: str
    summary: str
    operations: list[ChangeOperation] = Field(min_length=1)
    contradictions: list[Contradiction]
    validation_result: ValidationResult | None = None
    status: Literal["pending", "applied", "rejected", "reverted"] = "pending"
```

- [ ] **Step 3: 实现 append-safe store**

Pending 写入 `.vid2note/changes/pending/<id>.json`；应用后以原子移动进入 `applied/`；拒绝进入 `rejected/`。文件内容不可原地覆盖，修订生成新 ChangeSet 并通过 `supersedes` 关联。

- [ ] **Step 4: 运行模型/store tests**

Run: `uv run pytest core/tests/unit/wiki/test_models.py core/tests/unit/wiki/test_store.py -q`

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add core/src/vid2note_core/wiki/models.py core/src/vid2note_core/wiki/store.py core/tests/unit/wiki/test_models.py core/tests/unit/wiki/test_store.py
git commit -m "feat(wiki): define persistent changesets"
```

### Task 2: 实现 index.md 维护与 index-first retrieval

- [ ] **Step 1: 写索引解析与检索顺序测试**

```python
def test_retrieval_reads_schema_then_index_before_pages(recording_repo):
    result = retriever.find_context("AI POC 为什么失败")
    assert recording_repo.read_order[:2] == ["AGENTS.md", "index.md"]
    assert result.pages[0].path == "wiki/concepts/poc-trap.md"
```

- [ ] **Step 2: 实现确定性 IndexEntry**

```python
class IndexEntry(BaseModel):
    page_id: str
    title: str
    path: str
    summary: str
    page_type: Literal["concept", "entity", "topic", "comparison"]
    source_count: int
    updated: date
```

- [ ] **Step 3: 实现 index parser/renderer**

输出按 page type 和 title 稳定排序，保留用户位于 `<!-- user-notes:start/end -->` 内的内容。每条格式固定为 `- [[path|title]] — summary；N 个来源。`。

- [ ] **Step 4: 实现 retrieval**

先按 index 标题/摘要 token 匹配，再读取最多 12 个候选页面；不足时对 `wiki/`、`sources/`、`raw/*/transcript.md` 依次做普通文本扫描。返回值标记 `knowledge_layer`，不混淆 Wiki 结论与临时来源推断。

- [ ] **Step 5: 运行 index/retrieval tests**

Run: `uv run pytest core/tests/unit/wiki/test_index.py core/tests/unit/wiki/test_retrieval.py -q`

Expected: PASS and no vector/embedding imports.

- [ ] **Step 6: 提交**

```bash
git add core/src/vid2note_core/wiki/index.py core/src/vid2note_core/wiki/retrieval.py core/tests/unit/wiki/test_index.py core/tests/unit/wiki/test_retrieval.py
git commit -m "feat(wiki): add index-first retrieval"
```

### Task 3: 生成结构化 Wiki proposal

- [ ] **Step 1: 写 fake LLM compiler 场景测试**

```python
def test_second_source_updates_existing_page(compiler, second_source):
    result = compiler.propose(second_source)
    assert result.changeset is not None
    assert result.changeset.operations[0].action == "update"
    assert result.changeset.operations[0].page_id == "concept_ai_delivery"

def test_duplicate_claim_does_not_append_duplicate_paragraph(compiler, duplicate_source):
    result = compiler.propose(duplicate_source)
    assert result.changeset is None
    assert result.classification == "duplicate"

def test_conflicting_claims_are_preserved_as_contradiction(compiler, conflicting_source):
    result = compiler.propose(conflicting_source)
    assert result.changeset is not None
    assert len(result.changeset.contradictions) == 1
    assert "观点 A" in result.changeset.operations[0].after
    assert "观点 B" in result.changeset.operations[0].after
```

- [ ] **Step 2: 定义 Compiler 输入/输出边界**

```python
class CompileInput(BaseModel):
    source: SourceRecord
    source_note: VaultPage
    schema_text: str
    index_text: str
    related_pages: list[VaultPage]

class CompileResult(BaseModel):
    classification: Literal["new", "enhancement", "duplicate", "correction", "contradiction", "gap"]
    changeset: ChangeSet | None

class WikiCompiler:
    def propose(self, request: CompileInput) -> CompileResult:
        raise NotImplementedError
```

- [ ] **Step 3: 编写 `wiki_ingest.txt` prompt**

Prompt 明确要求把每条信息分类为新增、增强、重复、修正、矛盾或缺口；输出只允许 ChangeSet JSON；关键主张必须引用时间区间；不得删除旧矛盾；不得创造 schema 外页面类型。

- [ ] **Step 4: 实现严格 JSON parse 与一次修复重试**

模型输出先由 Pydantic 校验；无效时将 validation errors 作为修复输入重试一次，仍失败抛出 `WIKI_INVALID_CHANGESET`，不写 pending 文件。

- [ ] **Step 5: 把 `propose_wiki_changes` 节点接在 `register_source` 后**

节点输出 ChangeSet id；默认 A 模式只保存 pending，不写 Wiki。

- [ ] **Step 6: 运行 compiler/pipeline tests**

Run: `uv run pytest core/tests/unit/wiki/test_compiler.py core/tests/unit/pipeline/test_real_nodes.py -q`

Expected: PASS.

- [ ] **Step 7: 提交**

```bash
git add core/src/vid2note_core/wiki/compiler.py core/src/vid2note_core/prompts/wiki_ingest.txt core/src/vid2note_core/pipeline/real_nodes.py core/tests/unit/wiki/test_compiler.py core/tests/unit/pipeline/test_real_nodes.py
git commit -m "feat(wiki): propose changes from new sources"
```

### Task 4: 校验 frontmatter、双链、证据和 base hash

- [ ] **Step 1: 写 validator 失败矩阵**

覆盖缺失/变化 page id、非法 type、未知 source id、越界时间、broken wikilink、create path 已存在、update base hash 过期、`before` 不匹配、无 citation 的关键事实。

- [ ] **Step 2: 使用 Task 1 的 ValidationIssue 生成完整问题列表**

```python
issues = validator.validate(changeset).issues
assert all(issue.code and issue.message for issue in issues)
assert all(issue.severity in {"error", "warning"} for issue in issues)
```

- [ ] **Step 3: 实现 `ChangeSetValidator.validate`**

校验只读取正式 Vault 和 SourceRecord；不得修改 ChangeSet 或文件。关键事实引用启发式先覆盖数字、引号、专名密集句与“根据视频”声明，warning 可人工批准，越界或未知来源必须 error。

- [ ] **Step 4: 运行 validator tests**

Run: `uv run pytest core/tests/unit/wiki/test_validator.py -q`

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add core/src/vid2note_core/wiki/validator.py core/tests/unit/wiki/test_validator.py
git commit -m "feat(wiki): validate wiki changes and evidence"
```

### Task 5: 原子多文件应用、快照与回滚

- [ ] **Step 1: 写故障注入测试**

```python
def test_apply_failure_leaves_all_live_files_unchanged(applier, changeset, snapshot, fail_after_first_replace):
    with pytest.raises(OSError):
        applier.apply(changeset)
    assert snapshot.capture_live_bytes() == snapshot.before

def test_apply_updates_pages_index_and_log_together(applier, changeset):
    applier.apply(changeset)
    assert "new claim" in applier.repository.read_page("wiki/concepts/topic.md").content
    assert "topic" in applier.repository.read_page("index.md").content
    assert changeset.id in applier.repository.read_page("log.md").content

def test_revert_restores_exact_pre_apply_bytes(applier, changeset, snapshot):
    applier.apply(changeset)
    applier.revert(changeset.id)
    assert snapshot.capture_live_bytes() == snapshot.before
```

- [ ] **Step 2: 实现事务目录**

`.vid2note/transactions/<changeset_id>/` 包含 `before/`、`after/`、`manifest.json`。先复制所有受影响 live bytes 到 before，生成 after 并完整校验，再逐项 `os.replace`；manifest 记录每步状态供启动恢复。

- [ ] **Step 3: 定义恢复规则**

若进程在 commit 中断：manifest 全部 committed 时完成归档；否则使用 before 恢复所有 live paths。恢复后追加 `transaction-recovered` 日志，绝不依赖 SQLite 才能修复文件。

- [ ] **Step 4: 实现回滚为新的审计操作**

回滚读取 applied snapshot，校验当前 hash 未被外部编辑；有冲突则产生 pending revert ChangeSet，不覆盖用户修改。无冲突时恢复、更新 index/log，将原 ChangeSet 标为 reverted。

- [ ] **Step 5: 运行 applier/recovery tests**

Run: `uv run pytest core/tests/unit/wiki/test_applier.py -q`

Expected: PASS including injected failure after first replacement.

- [ ] **Step 6: 提交**

```bash
git add core/src/vid2note_core/wiki/applier.py core/tests/unit/wiki/test_applier.py
git commit -m "feat(wiki): apply and revert changes atomically"
```

### Task 6: 实现 A/B/C 自治策略与审批 API

- [ ] **Step 1: 写策略矩阵测试**

```python
@pytest.mark.parametrize(("mode", "kind", "decision"), [
    ("approval", "enhancement", "require_approval"),
    ("auto-revertible", "enhancement", "auto_apply"),
    ("high-autonomy", "contradiction", "require_approval"),
    ("high-autonomy", "correction", "require_approval"),
])
def test_policy(mode, kind, decision):
    assert AutonomyPolicy(mode).decide(kind) == decision
```

- [ ] **Step 2: 实现单一 `AutonomyMode` 配置**

模式存在 Knowledge Service config 中，API、标题栏和 Agent 面板从同一 endpoint 读取；默认必须是 `approval`。

- [ ] **Step 3: 暴露 ChangeSet API**

```text
GET  /api/v1/changesets?status=pending
GET  /api/v1/changesets/{id}
POST /api/v1/changesets/{id}/approve
POST /api/v1/changesets/{id}/reject
POST /api/v1/changesets/{id}/revert
POST /api/v1/changesets/{id}/revise
```

Approve 支持 operation indexes；部分批准生成一个只含选中 operation 的 derived ChangeSet 并保留 parent id。

- [ ] **Step 4: 重新生成 contracts 并运行 API tests**

Run: `uv run pytest server/tests/integration/test_changesets_api.py -q && npm --prefix desktop run contracts:export && npm --prefix desktop run contracts:generate`

Expected: PASS; schema contains ChangeSet and AutonomyMode.

- [ ] **Step 5: 提交**

```bash
git add core/src/vid2note_core/wiki/policy.py server/src/vid2note_server/api/changesets.py server/src/vid2note_server/schemas/changesets.py server/tests/integration/test_changesets_api.py desktop/openapi.json desktop/src/renderer/api/generated/schema.ts
git commit -m "feat(wiki): add approval and autonomy policies"
```

### Task 7: Wiki lint、完整场景与 Phase 3 验收

- [ ] **Step 1: 实现 lint 报告**

检查矛盾、陈旧 claim、孤儿页、缺失页面、broken link、缺失 citation、index 漂移和可研究缺口。Lint 默认只报告，不直接修改 Wiki；修复建议必须进入 ChangeSet。

- [ ] **Step 2: 建立六个场景 fixtures**

```text
01-create-concept
02-enhance-existing
03-ignore-duplicate
04-correct-claim
05-preserve-contradiction
06-reject-stale-base-hash
```

每个 fixture 包含 before Vault、new source note、fake LLM response 和 expected ChangeSet/applied tree。

- [ ] **Step 3: 写两来源 MVP 场景测试**

断言 source B 的批准操作更新 source A 已创建的同一 page id；`index.md` source_count 变为 2；矛盾段同时保留两条带时间证据的观点。

- [ ] **Step 4: 运行阶段验收**

Run:

```bash
uv run pytest core/tests/unit/wiki core/tests/scenarios/wiki -q
uv run pytest server/tests/integration/test_changesets_api.py server/tests/integration/test_wiki_ingest.py -q
uv run ruff check .
uv run mypy core/src server/src
npm --prefix desktop run contracts:check
```

Expected: all commands exit 0; scenario 02 updates the existing page and scenario 05 preserves both claims.

- [ ] **Step 5: 更新 CodeGraph 并提交**

```bash
codegraph update
git add core/src/vid2note_core/wiki core/tests/unit/wiki core/tests/scenarios/wiki server/src/vid2note_server server/tests/integration desktop/openapi.json desktop/src/renderer/api/generated/schema.ts
git commit -m "test(wiki): verify compounding wiki scenarios"
```
