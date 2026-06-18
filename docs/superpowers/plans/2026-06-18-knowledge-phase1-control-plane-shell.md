# Knowledge Workspace Phase 1 Control Plane And Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 Pydantic/OpenAPI 到 TypeScript 的共享契约流程，并把现有视频能力迁入统一知识工作台外壳而不改变业务行为。

**Architecture:** FastAPI schema 是 HTTP 契约事实源，生成的 TypeScript 只供 Renderer 使用。Vue 外壳重新实现 `knowledge-workspace-v1` 的信息架构与 tokens，旧页面作为工作区路由嵌入；本阶段不实现 Vault 正文、Wiki Compiler 或 Agent 业务。

**Tech Stack:** FastAPI、Pydantic v2、OpenAPI、openapi-typescript、Vue 3、TypeScript、Pinia、Vue Router、Vitest、Playwright、Electron。

---

## 文件结构

- Create: `server/src/vid2note_server/schemas/common.py`
- Create: `server/src/vid2note_server/schemas/tasks.py`
- Create: `server/src/vid2note_server/schemas/events.py`
- Create: `server/src/vid2note_server/schemas/config.py`
- Create: `server/src/vid2note_server/schemas/__init__.py`
- Modify: `server/src/vid2note_server/api/process.py`
- Modify: `server/src/vid2note_server/api/tasks.py`
- Modify: `server/src/vid2note_server/api/upload.py`
- Modify: `server/src/vid2note_server/api/artifacts.py`
- Modify: `server/src/vid2note_server/api/config.py`
- Modify: `server/src/vid2note_server/api/models.py`
- Modify: `server/src/vid2note_server/api/logs.py`
- Modify: `server/src/vid2note_server/api/events.py`
- Modify: `server/src/vid2note_server/main.py`
- Create: `server/tests/contract/test_openapi.py`
- Create: `scripts/export_openapi.py`
- Create: `desktop/openapi.json`
- Create: `desktop/src/renderer/api/generated/schema.ts`
- Create: `desktop/src/renderer/api/client.ts`
- Create: `desktop/src/renderer/api/errors.ts`
- Create: `desktop/src/renderer/api/__tests__/errors.test.ts`
- Rename: `desktop/src/renderer/api/{process,task,config,models,sse}.js` → `.ts`
- Create: `desktop/tsconfig.json`
- Create: `desktop/tsconfig.node.json`
- Modify: `desktop/package.json`
- Modify: `desktop/vite.config.js`
- Create: `desktop/src/renderer/env.d.ts`
- Rename: `desktop/src/renderer/main.js` → `main.ts`
- Rename: `desktop/src/renderer/router/index.js` → `index.ts`
- Create: `desktop/src/renderer/stores/workspace.ts`
- Create: `desktop/src/renderer/components/workspace/ToolRail.vue`
- Create: `desktop/src/renderer/components/workspace/WorkspaceTree.vue`
- Create: `desktop/src/renderer/components/workspace/WorkspaceMain.vue`
- Create: `desktop/src/renderer/components/workspace/AgentPlaceholder.vue`
- Create: `desktop/src/renderer/components/workspace/ResizablePane.vue`
- Create: `desktop/src/renderer/layouts/WorkspaceLayout.vue`
- Create: `desktop/src/renderer/views/ImportWorkspace.vue`
- Modify: `desktop/src/renderer/App.vue`
- Modify: `desktop/src/renderer/styles/app.css`
- Create: `desktop/src/renderer/styles/tokens.css`
- Create: `desktop/src/renderer/styles/workspace.css`
- Create: `desktop/src/renderer/components/workspace/__tests__/WorkspaceLayout.test.ts`
- Create: `desktop/tests/e2e/test_workspace_shell.spec.js`

### Task 1: 集中 Pydantic HTTP schemas 与 ErrorEnvelope

- [ ] **Step 1: 写 OpenAPI 契约失败测试**

```python
def test_openapi_exposes_typed_task_event_and_error(client):
    schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]
    assert "TaskEvent" in components
    assert "ErrorEnvelope" in components
    assert components["ErrorEnvelope"]["required"] == [
        "code", "message", "user_message", "retryable", "component", "operation"
    ]
```

- [ ] **Step 2: 运行并确认 schema 缺失**

Run: `uv run pytest server/tests/contract/test_openapi.py -q`

Expected: FAIL because shared schemas do not exist.

- [ ] **Step 3: 定义公共模型**

```python
class ErrorEnvelope(BaseModel):
    code: str
    message: str
    user_message: str
    retryable: bool
    component: str
    operation: str
    details: dict[str, JsonValue] | None = None
    cause_id: str | None = None

class TaskEvent(BaseModel):
    task_id: str
    event_type: Literal["task.created", "task.started", "node.started", "node.completed", "task.completed", "task.failed", "task.interrupted"]
    progress: int = Field(ge=0, le=100)
    message: str | None = None
    timestamp: datetime
```

- [ ] **Step 4: 将路由内 BaseModel 移入 `schemas/` 并添加显式 response_model**

不改变现有 URL；`process` 与 `tasks` 继续共享同一 Task 资源，避免创建第二套任务真相源。

- [ ] **Step 5: 注册统一异常处理器**

`Vid2NoteError`、request validation 和未知错误都返回 `{"error": ErrorEnvelope}`；未知错误的 `message` 仅进日志，`user_message` 使用安全文案。

- [ ] **Step 6: 运行 contract 与 integration tests**

Run: `uv run pytest server/tests/contract server/tests/integration -q`

Expected: PASS.

- [ ] **Step 7: 提交**

```bash
git add server/src/vid2note_server/schemas server/src/vid2note_server/api server/src/vid2note_server/main.py server/tests
git commit -m "feat(contracts): centralize API schemas"
```

### Task 2: 生成并校验 TypeScript contracts

- [ ] **Step 1: 写 OpenAPI 导出脚本测试**

```python
def test_export_openapi_is_deterministic(tmp_path):
    first = export_schema(tmp_path / "a.json")
    second = export_schema(tmp_path / "b.json")
    assert first.read_bytes() == second.read_bytes()
```

- [ ] **Step 2: 实现稳定导出**

```python
def export_schema(destination: Path) -> Path:
    payload = json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True)
    destination.write_text(payload + "\n", encoding="utf-8")
    return destination
```

- [ ] **Step 3: 增加前端开发依赖与 scripts**

```json
{
  "scripts": {
    "contracts:export": "uv run python ../scripts/export_openapi.py openapi.json",
    "contracts:generate": "openapi-typescript openapi.json -o src/renderer/api/generated/schema.ts",
    "contracts:check": "npm run contracts:export && npm run contracts:generate && git diff --exit-code -- openapi.json src/renderer/api/generated/schema.ts",
    "typecheck": "vue-tsc --noEmit",
    "test:unit": "vitest run"
  },
  "devDependencies": {
    "openapi-typescript": "^7.6.1",
    "@vue/test-utils": "^2.4.6",
    "jsdom": "^25.0.1",
    "typescript": "^5.6.3",
    "vite": "^5.0.0",
    "vitest": "^2.1.8",
    "vue-tsc": "^2.2.0"
  }
}
```

保留原有依赖字段，只合并上面的 scripts/devDependencies。
同时在 `vite.config.js` 增加 `test: { environment: 'jsdom', globals: true }`，使 Renderer 组件测试使用同一 Vite alias 和 Vue plugin。

- [ ] **Step 4: 生成 schema 并检查关键类型**

Run: `cd desktop && npm install && npm run contracts:export && npm run contracts:generate && rg -n 'ErrorEnvelope|TaskEvent' src/renderer/api/generated/schema.ts`

Expected: generated file contains both interfaces.

- [ ] **Step 5: 运行漂移检查**

Run: `npm --prefix desktop run contracts:check`

Expected: exit 0 after generated files are staged or clean.

- [ ] **Step 6: 提交**

```bash
git add scripts/export_openapi.py server/tests/contract desktop/package.json desktop/package-lock.json desktop/openapi.json desktop/src/renderer/api/generated/schema.ts
git commit -m "feat(contracts): generate renderer types from OpenAPI"
```

### Task 3: 建立类型化 API client 与错误处理

- [ ] **Step 1: 写 client 错误解析单测**

```typescript
it('preserves ErrorEnvelope fields', () => {
  const error = toApiError({ response: { data: { error: envelope } } })
  expect(error.code).toBe('DOWNLOAD_TIMEOUT')
  expect(error.retryable).toBe(true)
})
```

- [ ] **Step 2: 运行并确认 `toApiError` 不存在**

Run: `npm --prefix desktop run test:unit -- src/renderer/api/__tests__/errors.test.ts`

Expected: FAIL.

- [ ] **Step 3: 实现 `ApiError` 与 typed request wrapper**

```typescript
export class ApiError extends Error {
  constructor(public readonly envelope: ErrorEnvelope) {
    super(envelope.user_message)
  }
  get code() { return this.envelope.code }
  get retryable() { return this.envelope.retryable }
}
```

`client.ts` 只负责 base URL、短期 token、JSON 与 ErrorEnvelope；资源函数在各自 `.ts` 文件中声明 generated request/response 类型。

- [ ] **Step 4: 逐个迁移 process/task/config/models/sse 到 TypeScript**

不得用 `any` 绕过生成类型；SSE payload 先用 `TaskEvent` schema 校验终态字段。

- [ ] **Step 5: 运行单测与 typecheck**

Run: `npm --prefix desktop run test:unit && npm --prefix desktop run typecheck`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add desktop/src/renderer/api desktop/src/renderer/env.d.ts desktop/tsconfig.json desktop/tsconfig.node.json desktop/package.json desktop/package-lock.json
git commit -m "feat(contracts): add typed renderer API client"
```

### Task 4: 提取生产级视觉 tokens

- [ ] **Step 1: 写 token 存在性测试**

```typescript
it('exposes the workspace color and spacing contract', () => {
  expect(css).toContain('--color-accent: #2383e2')
  expect(css).toContain('--rail-width: 52px')
  expect(css).toContain('--focus-ring')
})
```

- [ ] **Step 2: 从模板和现有 `app.css` 提取 tokens**

`tokens.css` 必须定义浅/深主题、暖灰背景、白色阅读面、azure 强调、边框、正文/等宽字体 fallback、36/40px 点击目标、focus ring 和 reduced-motion。不得复制模板 inline style、手绘 SVG 或演示脚本。

- [ ] **Step 3: 把现有全局样式改为引用 tokens**

同一语义颜色只保留一个变量事实源；现有页面在迁移期间保持视觉可读，不做无关重排。

- [ ] **Step 4: 运行 unit/build**

Run: `npm --prefix desktop run test:unit && npm --prefix desktop run build`

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add desktop/src/renderer/styles desktop/src/renderer/components/workspace/__tests__
git commit -m "feat(workspace): establish workspace design tokens"
```

### Task 5: 实现统一四区外壳与响应式状态

- [ ] **Step 1: 写 WorkspaceLayout 组件测试**

```typescript
it('collapses tree below 1100 and opens agent as drawer below 850', async () => {
  viewport.value = 820
  const wrapper = mount(WorkspaceLayout)
  expect(wrapper.get('[data-testid="workspace-tree"]').attributes('aria-hidden')).toBe('true')
  expect(wrapper.get('[data-testid="agent-panel"]').classes()).toContain('is-drawer')
})
```

- [ ] **Step 2: 实现唯一 workspace store**

```typescript
export const useWorkspaceStore = defineStore('workspace', () => {
  const treeOpen = ref(true)
  const agentOpen = ref(true)
  const treeWidth = ref(272)
  const agentWidth = ref(380)
  const autonomyMode = ref<'approval' | 'auto-revertible' | 'high-autonomy'>('approval')
  return { treeOpen, agentOpen, treeWidth, agentWidth, autonomyMode }
})
```

- [ ] **Step 3: 实现 ToolRail/Tree/Main/AgentPlaceholder/ResizablePane**

所有图标来自现有 Element Plus icon 包；按钮必须有 accessible name、键盘焦点和至少 36×36px 命中区。拖拽宽度限定合理最小/最大值并写入 localStorage。

- [ ] **Step 4: 增加工作区路由**

```text
/workspace/import
/workspace/tasks/:id
/workspace/history
/workspace/mindmap/:id
/workspace/settings
```

旧 URL 只做 redirect，不保留第二套 shell。

- [ ] **Step 5: 运行组件测试和构建**

Run: `npm --prefix desktop run test:unit && npm --prefix desktop run typecheck && npm --prefix desktop run build`

Expected: PASS.

- [ ] **Step 6: 提交**

```bash
git add desktop/src/renderer/components/workspace desktop/src/renderer/layouts desktop/src/renderer/stores/workspace.ts desktop/src/renderer/router desktop/src/renderer/App.vue desktop/src/renderer/styles
git commit -m "feat(workspace): add the unified desktop shell"
```

### Task 6: 迁移旧能力并完成 Phase 1 E2E

- [ ] **Step 1: 将 Home 重命名/包装为 ImportWorkspace**

复用现有任务创建 store 与 API；任务详情、历史、思维导图和设置只迁入主阅读区，不重写业务。

- [ ] **Step 2: 写 shell E2E**

```javascript
test('legacy video workflow runs inside one workspace shell', async ({ page }) => {
  await page.goto('/workspace/import')
  await expect(page.getByRole('navigation', { name: '主工具' })).toBeVisible()
  await expect(page.getByTestId('workspace-main')).toBeVisible()
  await page.getByRole('link', { name: '设置' }).click()
  await expect(page).toHaveURL(/workspace\/settings/)
  await expect(page.getByRole('navigation', { name: '主工具' })).toBeVisible()
})
```

- [ ] **Step 3: 验证断点与键盘路径**

Playwright 分别使用 1440、1024、820 宽度断言文件树/Agent 的折叠行为，并用 Tab 到达工具轨、主阅读区和面板开关。

- [ ] **Step 4: 运行阶段验收**

Run:

```bash
uv run pytest server/tests/contract server/tests/integration -q
npm --prefix desktop run contracts:check
npm --prefix desktop run test:unit
npm --prefix desktop run typecheck
npm --prefix desktop run build
npm --prefix desktop run test:e2e -- test_workspace_shell.spec.js
```

Expected: all commands exit 0; old workflows render in one shell.

- [ ] **Step 5: 更新 CodeGraph 并提交**

```bash
codegraph update
git add desktop/src/renderer desktop/tests/e2e/test_workspace_shell.spec.js
git commit -m "feat(workspace): migrate legacy views into the workspace shell"
```
