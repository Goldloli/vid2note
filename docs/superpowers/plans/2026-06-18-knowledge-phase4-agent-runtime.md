# Knowledge Workspace Phase 4 Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Built-in、Codex CLI 与 Claude Code 三种 Runtime，使其用统一事件基于 Wiki 回答，并且只能通过 ChangeSet 建议写回。

**Architecture:** Registry 负责检测和 capability negotiation；Session service 负责统一生命周期与 SSE；Built-in Runtime 使用白名单 Python tools；外部 CLI 只在包含必要页面的临时工作区运行，文件 diff 转换为 ChangeSet 后由 Wiki Applier 决定是否写正式 Vault。前端和 Server 永不解析厂商原生事件之外的第二套模型。

**Tech Stack:** Python asyncio subprocess、Pydantic、FastAPI SSE、SQLite session metadata、现有 LLM adapters、pytest fake CLI、recorded JSONL fixtures。

---

## 文件结构

- Create: `core/src/vid2note_core/agents/models.py`
- Create: `core/src/vid2note_core/agents/runtime.py`
- Create: `core/src/vid2note_core/agents/registry.py`
- Create: `core/src/vid2note_core/agents/events.py`
- Create: `core/src/vid2note_core/agents/session.py`
- Create: `core/src/vid2note_core/agents/tools.py`
- Create: `core/src/vid2note_core/agents/builtin.py`
- Create: `core/src/vid2note_core/agents/workspace.py`
- Create: `core/src/vid2note_core/agents/sandbox.py`
- Create: `core/src/vid2note_core/agents/subprocess.py`
- Create: `core/src/vid2note_core/agents/adapters/codex.py`
- Create: `core/src/vid2note_core/agents/adapters/claude.py`
- Create: `core/src/vid2note_core/agents/parsers/codex_jsonl.py`
- Create: `core/src/vid2note_core/agents/parsers/claude_stream.py`
- Create: `core/src/vid2note_core/agents/prompts/query.txt`
- Create: `core/tests/unit/agents/test_models.py`
- Create: `core/tests/unit/agents/test_events.py`
- Create: `core/tests/unit/agents/test_registry.py`
- Create: `core/tests/unit/agents/test_tools.py`
- Create: `core/tests/unit/agents/test_builtin.py`
- Create: `core/tests/unit/agents/test_workspace.py`
- Create: `core/tests/unit/agents/test_sandbox.py`
- Create: `core/tests/unit/agents/test_subprocess.py`
- Create: `core/tests/unit/agents/test_codex_parser.py`
- Create: `core/tests/unit/agents/test_codex_adapter.py`
- Create: `core/tests/unit/agents/test_claude_parser.py`
- Create: `core/tests/unit/agents/test_claude_adapter.py`
- Create: `core/tests/fixtures/agents/codex/success.jsonl`
- Create: `core/tests/fixtures/agents/codex/failure-and-unknown.jsonl`
- Create: `core/tests/fixtures/agents/claude/success.jsonl`
- Create: `core/tests/fixtures/agents/claude/resume-missing.jsonl`
- Create: `core/tests/fake_cli/fake_codex.py`
- Create: `core/tests/fake_cli/fake_claude.py`
- Create: `server/src/vid2note_server/schemas/agents.py`
- Create: `server/src/vid2note_server/api/agents.py`
- Create: `server/tests/integration/test_agents_api.py`
- Create: `server/tests/integration/test_agent_sse.py`
- Modify: `server/src/vid2note_server/dependencies.py`
- Modify: `server/src/vid2note_server/main.py`

### Task 1: 定义统一 Runtime、capabilities 与 AgentEvent

- [ ] **Step 1: 写事件序列和终态唯一测试**

```python
def test_run_has_one_started_and_one_terminal_event(events):
    assert [event.type for event in events].count("run.started") == 1
    assert sum(event.type in TERMINAL_EVENT_TYPES for event in events) == 1

def test_unknown_native_event_becomes_diagnostic_not_failure(parser):
    events = parser.parse_line('{"type":"future.event","value":1}')
    assert events == []
    assert parser.diagnostics[-1].code == "unknown_native_event"

def test_event_json_round_trip_is_stable(agent_event):
    assert AgentEvent.model_validate_json(agent_event.model_dump_json()) == agent_event
```

- [ ] **Step 2: 定义模型**

```python
class AgentCapabilities(BaseModel):
    streaming: bool
    resume: bool
    file_edits: bool
    media_requests: bool
    models: list[str]

class DetectionResult(BaseModel):
    available: bool
    version: str | None
    auth_status: Literal["authenticated", "unauthenticated", "unknown"]
    reason: str | None = None

class AgentRunInput(BaseModel):
    run_id: str
    session_id: str
    message: str
    context_paths: list[str]
    model: str | None = None

class AgentEvent(BaseModel):
    run_id: str
    sequence: int = Field(ge=0)
    type: Literal[
        "run.started", "thinking.delta", "message.delta", "tool.started",
        "tool.completed", "file.observed", "changeset.proposed",
        "approval.required", "usage", "run.completed", "run.failed", "run.cancelled"
    ]
    timestamp: datetime
    payload: dict[str, JsonValue]
```

- [ ] **Step 3: 定义 Protocol**

```python
class AgentRuntime(Protocol):
    id: str
    async def detect(self) -> DetectionResult:
        raise NotImplementedError
    def capabilities(self) -> AgentCapabilities:
        raise NotImplementedError
    def run(self, input: AgentRunInput) -> AsyncIterator[AgentEvent]:
        raise NotImplementedError
    async def cancel(self, run_id: str) -> None:
        raise NotImplementedError
    def resume(self, session_id: str, message: str) -> AsyncIterator[AgentEvent]:
        raise NotImplementedError
```

- [ ] **Step 4: 实现 sequence/terminal guard**

所有 Runtime 通过同一 emitter 生成递增 sequence；发出终态后拒绝任何新事件；异常统一为 `run.failed` ErrorEnvelope。

- [ ] **Step 5: 运行模型测试并提交**

Run: `uv run pytest core/tests/unit/agents/test_models.py core/tests/unit/agents/test_events.py -q`

```bash
git add core/src/vid2note_core/agents/models.py core/src/vid2note_core/agents/runtime.py core/src/vid2note_core/agents/events.py core/tests/unit/agents
git commit -m "feat(agent): define normalized runtime events"
```

### Task 2: Registry 检测、版本与认证状态

- [ ] **Step 1: 写 detection 测试**

Fake runner 覆盖 CLI 缺失、版本成功、认证失败、探测超时；检测不得发起付费模型调用。

- [ ] **Step 2: 实现声明式 RuntimeDescriptor**

```python
class RuntimeDescriptor(BaseModel):
    id: str
    label: str
    executable: str | None
    version_args: list[str]
    auth_args: list[str] | None
    detection_timeout_ms: int = 5000
```

- [ ] **Step 3: 注册三种 Runtime**

Built-in 永远 available；Codex 使用 `codex --version` 与 `codex login status`；Claude 使用 `claude --version` 与 `claude auth status`。认证命令不支持时返回 `unknown`，不假装 authenticated。

- [ ] **Step 4: 缓存短时检测结果并支持手动 refresh**

缓存 TTL 30 秒；PATH 或设置变化时清除。Registry 只返回能力和诊断，不自动 fallback。

- [ ] **Step 5: 运行并提交**

Run: `uv run pytest core/tests/unit/agents/test_registry.py -q`

```bash
git add core/src/vid2note_core/agents/registry.py core/tests/unit/agents/test_registry.py
git commit -m "feat(agent): detect built-in and CLI runtimes"
```

### Task 3: Built-in Runtime 白名单工具循环

- [ ] **Step 1: 写工具权限测试**

```python
def test_builtin_tools_have_no_shell_or_arbitrary_write():
    assert set(toolbox.names()) == {
        "read_schema", "read_index", "read_page", "read_source",
        "search_text", "propose_changeset", "request_media"
    }
```

- [ ] **Step 2: 实现类型化工具**

每个工具接收 Pydantic args；所有 path 通过 VaultRepository；`propose_changeset` 只调用 ChangeSetStore；`request_media` 只调用 MediaCitationService；不存在 shell、任意 URL、任意文件写入。

- [ ] **Step 3: 实现固定 query 顺序**

系统 prompt 强制 `read_schema` → `read_index` → 相关 pages → 必要时 sources；回答 payload 将 claim 分类为 `wiki`、`source` 或 `inference` 并绑定 citations。

- [ ] **Step 4: 实现 tool loop 上限**

单轮最多 20 个工具调用、最大 12 个 Wiki pages、最大 6 个 source excerpts；达到上限返回带 evidence gap 的正常回答，不无限循环。

- [ ] **Step 5: 运行 Built-in tests**

Run: `uv run pytest core/tests/unit/agents/test_tools.py core/tests/unit/agents/test_builtin.py -q`

Expected: PASS and recording repository confirms index-first order.

- [ ] **Step 6: 提交**

```bash
git add core/src/vid2note_core/agents/tools.py core/src/vid2note_core/agents/builtin.py core/src/vid2note_core/agents/prompts/query.txt core/tests/unit/agents
git commit -m "feat(agent): add the built-in wiki runtime"
```

### Task 4: 创建外部 Agent 临时工作区与 diff guard

- [ ] **Step 1: 写隔离测试**

```python
def test_workspace_contains_only_selected_context(workspace):
    assert workspace.relative_files() == {
        "AGENTS.md", "index.md", "wiki/concepts/poc-trap.md", "sources/src_a--talk.md", "run-manifest.json"
    }

def test_cli_edit_never_changes_live_vault(workspace, live_snapshot):
    workspace.write_text("wiki/concepts/poc-trap.md", "changed in sandbox")
    assert live_snapshot.capture() == live_snapshot.before

def test_diff_rejects_binary_symlink_and_out_of_scope_paths(workspace, tmp_path):
    workspace.write_bytes("wiki/binary.bin", b"\x00")
    workspace.symlink("wiki/escape.md", tmp_path / "outside.md")
    with pytest.raises(AgentWorkspaceViolation):
        workspace.collect_diff()
```

- [ ] **Step 2: 实现 `AgentWorkspace.create`**

目录位于 `.vid2note/agent-runs/<run_id>/workspace`；复制 `AGENTS.md`、`index.md`、选中的 Wiki/source 文本和最小 manifest。Raw original media 不复制；media tool 通过受控请求单独生成。

- [ ] **Step 3: 记录 baseline manifest**

Manifest 为每个允许 Markdown 文件保存 path + SHA-256；CLI 结束后只接受 `.md` 文件 create/update/rename，拒绝 delete、symlink、binary、root escape 与未声明目录。

- [ ] **Step 4: 将合法 diff 转为 ChangeSet**

每个 operation 的 `base_hash` 来自正式 Vault 当前值而非临时副本；正式 Vault 在运行期间变化时 ChangeSet 保持 pending conflict，绝不覆盖。

- [ ] **Step 5: 清理策略**

成功且已持久化 ChangeSet 后删除 workspace；失败 workspace 保留 24 小时供诊断，但日志和 manifest 不包含密钥。

- [ ] **Step 6: 运行并提交**

Run: `uv run pytest core/tests/unit/agents/test_workspace.py -q`

```bash
git add core/src/vid2note_core/agents/workspace.py core/tests/unit/agents/test_workspace.py
git commit -m "feat(agent): isolate external CLI workspaces"
```

### Task 5: 实现可取消的 subprocess runner

- [ ] **Step 1: 写 stdin、超时、取消、崩溃测试**

Fake CLI 验证长 prompt 经 stdin 传递；取消先 SIGTERM，5 秒后 SIGKILL；stderr 被限制为 64 KiB 并脱敏。

增加安全测试：fake CLI 尝试读取正式 Vault 和在 workspace 外写文件时必须失败；若当前平台没有可用的强制隔离实现，Codex/Claude detection 必须返回 `available=false`、reason=`sandbox_unavailable`，不能降级为仅靠 prompt 约束。

- [ ] **Step 2: 实现 runner**

```python
process = await asyncio.create_subprocess_exec(
    executable, *args,
    cwd=workspace,
    env=sanitized_env,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

环境变量使用 allowlist；移除 Vault/应用密钥，仅保留 CLI 自身认证环境与 PATH/HOME。不得使用 `shell=True`。

`SandboxPolicy` 将允许写目录限定为本次 workspace 和该 Runtime 的临时 HOME，将正式 Vault、其他 data-root 和用户目录设为不可读写；网络只允许 Runtime 自身连接模型服务。macOS 首版使用独立 profile 包裹子进程，Codex 自带 `workspace-write` 仍作为第二层；无法证明 profile 生效时拒绝启动外部 Runtime。

- [ ] **Step 3: 实现逐行 JSONL backpressure**

限制单行 1 MiB；未知/无效行转为诊断事件并计数，超过 20 条无效行终止为 `AGENT_PROTOCOL_ERROR`。

- [ ] **Step 4: 运行并提交**

Run: `uv run pytest core/tests/unit/agents/test_subprocess.py core/tests/unit/agents/test_sandbox.py -q`

```bash
git add core/src/vid2note_core/agents/subprocess.py core/src/vid2note_core/agents/sandbox.py core/tests/fake_cli core/tests/unit/agents/test_subprocess.py core/tests/unit/agents/test_sandbox.py
git commit -m "feat(agent): run CLI agents with cancellation and limits"
```

### Task 6: Codex Adapter 与录制事件回放

- [ ] **Step 1: 创建录制 fixtures 与 parser tests**

覆盖 started、reasoning、message、tool、usage、completed、failed、unknown event。Fixture 是脱敏 JSONL，不来自真实用户会话。

- [ ] **Step 2: 构造固定 argv**

```python
args = [
    "exec", "--json", "--skip-git-repo-check",
    "--sandbox", "workspace-write",
    "-c", "sandbox_workspace_write.network_access=false",
    "-c", 'default_permissions=":workspace"',
    "-C", str(workspace),
]
```

Prompt 只经 stdin。禁止 `danger-full-access`、`--add-dir` 指向正式 Vault 或用户目录；model/reasoning 只从 validated options 追加。

- [ ] **Step 3: 映射 JSONL 到 AgentEvent**

原生 thread/session id 保存到 session metadata；file changes 只发 `file.observed`，最终由 workspace diff 生成单个 `changeset.proposed`。

- [ ] **Step 4: 运行 adapter tests**

Run: `uv run pytest core/tests/unit/agents/test_codex_parser.py core/tests/unit/agents/test_codex_adapter.py -q`

Expected: PASS without installed Codex or network.

- [ ] **Step 5: 提交**

```bash
git add core/src/vid2note_core/agents/adapters/codex.py core/src/vid2note_core/agents/parsers/codex_jsonl.py core/tests/fixtures/agents/codex core/tests/unit/agents/test_codex_*.py
git commit -m "feat(agent): add the Codex CLI adapter"
```

### Task 7: Claude Code Adapter 与受控 resume

- [ ] **Step 1: 创建 stream-json fixtures 与 parser tests**

覆盖 system/session id、assistant partial、tool_use、tool_result、result、auth failure、missing resume、unknown event。

- [ ] **Step 2: 构造固定 argv**

```python
args = [
    "-p", "--input-format", "stream-json",
    "--output-format", "stream-json", "--verbose",
    "--permission-mode", "bypassPermissions",
]
```

`bypassPermissions` 只因 CWD 是隔离 workspace 且进程没有正式 Vault/额外目录访问；不得传 `--add-dir`。新会话传 `--session-id <uuid>`，续传传 `--resume <stored_id>`，不能同时传。

- [ ] **Step 3: 实现 stream-json stdin envelope**

初始消息和续传消息使用 Claude stream-json 要求的 user message JSONL；输入结束后关闭 stdin。缺失 resume session 时产生明确 `AGENT_RESUME_MISSING`，由用户选择新会话，不静默 fallback。

- [ ] **Step 4: 运行 adapter tests**

Run: `uv run pytest core/tests/unit/agents/test_claude_parser.py core/tests/unit/agents/test_claude_adapter.py -q`

Expected: PASS without installed Claude or network.

- [ ] **Step 5: 提交**

```bash
git add core/src/vid2note_core/agents/adapters/claude.py core/src/vid2note_core/agents/parsers/claude_stream.py core/tests/fixtures/agents/claude core/tests/unit/agents/test_claude_*.py
git commit -m "feat(agent): add the Claude Code adapter"
```

### Task 8: Session API、SSE 与 Phase 4 验收

- [ ] **Step 1: 实现 Session service 状态机**

```text
created → running → completed | failed | cancelled
completed → running only through explicit resume/new message
```

SQLite 保存 session/run metadata 和小型事件索引；完整知识仍在 Vault，事件日志不得包含密钥或未脱敏 prompt。

- [ ] **Step 2: 暴露 endpoints**

```text
GET  /api/v1/agents
POST /api/v1/agent/sessions
POST /api/v1/agent/sessions/{id}/messages
GET  /api/v1/agent/sessions/{id}/events
POST /api/v1/agent/runs/{id}/cancel
```

- [ ] **Step 3: 写 SSE 终态与取消集成测试**

断言 sequence 单调、started 唯一、terminal 唯一、断开订阅不取消 run、显式 cancel 才终止；ChangeSet id 可由 API 读取且正式 Vault 未变。

- [ ] **Step 4: 重新生成 contracts**

Run: `npm --prefix desktop run contracts:export && npm --prefix desktop run contracts:generate`

Expected: schema contains AgentEvent, AgentCapabilities, AgentSession.

- [ ] **Step 5: 运行阶段验收**

Run:

```bash
uv run pytest core/tests/unit/agents -q
uv run pytest server/tests/integration/test_agents_api.py server/tests/integration/test_agent_sse.py -q
uv run ruff check .
uv run mypy core/src server/src
npm --prefix desktop run contracts:check
```

Expected: all commands exit 0; Built-in and both fake CLIs answer from the same Wiki fixture and propose ChangeSets without changing live files.

- [ ] **Step 6: 更新 CodeGraph 并提交**

```bash
codegraph update
git add core/src/vid2note_core/agents core/tests/unit/agents core/tests/fixtures/agents core/tests/fake_cli server/src/vid2note_server server/tests/integration desktop/openapi.json desktop/src/renderer/api/generated/schema.ts
git commit -m "feat(agent): expose normalized agent sessions"
```
