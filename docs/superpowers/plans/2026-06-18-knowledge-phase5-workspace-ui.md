# Knowledge Workspace Phase 5 Complete Workspace UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成四区可调知识工作台和四类专注视图，让用户只通过桌面 UI 完成导入、审批、阅读/编辑、Agent 问答、媒体证据回看和 Wiki 健康维护。

**Architecture:** 所有视图共享 WorkspaceLayout、generated API contracts、Pinia stores 和 tokens；Wiki/Source/ChangeSet/Agent 各有独立 store，组件不直接调用 axios。Markdown 阅读使用安全 renderer，源码编辑与 Diff 使用 CodeMirror 6；媒体证据卡只消费类型化 MediaReference。

**Tech Stack:** Vue 3、TypeScript、Pinia、Vue Router、CodeMirror 6/Merge、markdown-it、DOMPurify、Element Plus icons、Vitest、Playwright、Electron。

---

## 文件结构

- Modify: `desktop/package.json`
- Create: `desktop/src/renderer/api/vault.ts`
- Create: `desktop/src/renderer/api/changesets.ts`
- Create: `desktop/src/renderer/api/agents.ts`
- Create: `desktop/src/renderer/api/media.ts`
- Create: `desktop/src/renderer/stores/vault.ts`
- Create: `desktop/src/renderer/stores/changesets.ts`
- Create: `desktop/src/renderer/stores/agent.ts`
- Create: `desktop/src/renderer/stores/media.ts`
- Create: `desktop/src/renderer/components/wiki/WikiTree.vue`
- Create: `desktop/src/renderer/components/wiki/WikiSearch.vue`
- Create: `desktop/src/renderer/components/wiki/MarkdownReader.vue`
- Create: `desktop/src/renderer/components/wiki/MarkdownEditor.vue`
- Create: `desktop/src/renderer/components/wiki/PageOutline.vue`
- Create: `desktop/src/renderer/components/wiki/BacklinksPanel.vue`
- Create: `desktop/src/renderer/components/source/SourceTimeline.vue`
- Create: `desktop/src/renderer/components/source/SourcePlayer.vue`
- Create: `desktop/src/renderer/components/source/EvidenceCard.vue`
- Create: `desktop/src/renderer/components/changeset/ChangeSetList.vue`
- Create: `desktop/src/renderer/components/changeset/DiffReview.vue`
- Create: `desktop/src/renderer/components/changeset/ContradictionPanel.vue`
- Create: `desktop/src/renderer/components/agent/AgentPanel.vue`
- Create: `desktop/src/renderer/components/agent/AgentEventStream.vue`
- Create: `desktop/src/renderer/components/agent/AgentComposer.vue`
- Create: `desktop/src/renderer/components/agent/RuntimePicker.vue`
- Create: `desktop/src/renderer/views/WikiWorkspace.vue`
- Create: `desktop/src/renderer/views/SourceWorkspace.vue`
- Create: `desktop/src/renderer/views/ChangeSetWorkspace.vue`
- Create: `desktop/src/renderer/views/AgentWorkspace.vue`
- Create: `desktop/src/renderer/views/MediaToolsWorkspace.vue`
- Modify: `desktop/src/renderer/views/Settings.vue`
- Modify: `desktop/src/renderer/layouts/WorkspaceLayout.vue`
- Modify: `desktop/src/renderer/router/index.ts`
- Create: `desktop/src/renderer/components/wiki/WikiTree.test.ts`
- Create: `desktop/src/renderer/components/wiki/WikiSearch.test.ts`
- Create: `desktop/src/renderer/components/wiki/MarkdownReader.test.ts`
- Create: `desktop/src/renderer/components/wiki/MarkdownEditor.test.ts`
- Create: `desktop/src/renderer/components/source/SourcePlayer.test.ts`
- Create: `desktop/src/renderer/components/source/SourceTimeline.test.ts`
- Create: `desktop/src/renderer/components/source/EvidenceCard.test.ts`
- Create: `desktop/src/renderer/components/changeset/ChangeSetList.test.ts`
- Create: `desktop/src/renderer/components/changeset/DiffReview.test.ts`
- Create: `desktop/src/renderer/components/changeset/ContradictionPanel.test.ts`
- Create: `desktop/src/renderer/components/agent/AgentPanel.test.ts`
- Create: `desktop/src/renderer/components/agent/AgentEventStream.test.ts`
- Create: `desktop/src/renderer/components/agent/AgentComposer.test.ts`
- Create: `desktop/src/renderer/components/agent/RuntimePicker.test.ts`
- Create: `desktop/src/renderer/views/ImportWorkspace.test.ts`
- Create: `desktop/src/renderer/views/MediaToolsWorkspace.test.ts`
- Create: `desktop/src/renderer/views/Settings.test.ts`
- Create: `desktop/tests/e2e/test_knowledge_mvp.spec.js`
- Create: `desktop/tests/e2e/test_workspace_accessibility.spec.js`
- Create: `desktop/tests/e2e/test_workspace_responsive.spec.js`

### Task 1: 添加 UI 依赖与类型化资源 stores

- [ ] **Step 1: 安装固定依赖**

Run:

```bash
cd desktop
npm install @codemirror/state @codemirror/view @codemirror/lang-markdown @codemirror/merge markdown-it dompurify
npm install -D @types/markdown-it
```

Expected: package lock updates and `npm run typecheck` still exits 0.

- [ ] **Step 2: 写 store 并发/陈旧响应测试**

```typescript
it('does not replace the current page with a stale response', async () => {
  api.readPage.mockImplementation(path => deferred[path].promise)
  store.open('wiki/a.md')
  store.open('wiki/b.md')
  deferred['wiki/b.md'].resolve(pageB)
  deferred['wiki/a.md'].resolve(pageA)
  await flushPromises()
  expect(store.currentPage?.path).toBe('wiki/b.md')
})
```

- [ ] **Step 3: 实现四个 typed API modules**

函数参数和返回值都引用 generated schema；SSE 使用统一 decoder；没有 `any`、字段猜测或组件内 URL 拼接。

- [ ] **Step 4: 实现 Vault/ChangeSet/Agent/Media stores**

每个 store 负责 loading/error/cancel/stale response；`autonomyMode` 继续只来自 Phase 1 workspace store，并从 server config hydration，禁止 AgentPanel 私存第二份默认值。

- [ ] **Step 5: 运行测试与提交**

Run: `npm --prefix desktop run test:unit && npm --prefix desktop run typecheck`

```bash
git add desktop/package.json desktop/package-lock.json desktop/src/renderer/api desktop/src/renderer/stores
git commit -m "feat(workspace): add typed knowledge workspace stores"
```

### Task 2: Wiki Tree、搜索与文件状态

- [ ] **Step 1: 写树语义和默认折叠测试**

```typescript
it('renders raw collapsed and exposes pending count', () => {
  const wrapper = mount(WikiTree, { props: { tree, pendingCount: 3 } })
  expect(wrapper.get('[role="tree"]')).toBeTruthy()
  expect(wrapper.get('[data-path="raw"]').attributes('aria-expanded')).toBe('false')
  expect(wrapper.text()).toContain('3')
})
```

- [ ] **Step 2: 实现 TreeItem 键盘模型**

ArrowUp/Down 移动可见节点；ArrowRight 展开/进入子节点；ArrowLeft 折叠/回父节点；Enter 打开；焦点使用 roving tabindex。`wiki/`、`sources/`、`index.md`、`log.md` 优先，`raw/` 默认折叠。

- [ ] **Step 3: 实现普通文本搜索**

300ms debounce，显示 path、标题、命中摘要和知识层；搜索结果点击打开对应页面，不引入向量相关 UI 或术语。

- [ ] **Step 4: 显示外部修改与待审批状态**

Tree node 用文本/图标共同表达 modified/conflict/pending，不只依赖颜色。待审批数点击进入 ChangeSet 专注视图。

- [ ] **Step 5: 运行并提交**

Run: `npm --prefix desktop run test:unit -- WikiTree WikiSearch && npm --prefix desktop run typecheck`

```bash
git add desktop/src/renderer/components/wiki/WikiTree.vue desktop/src/renderer/components/wiki/WikiSearch.vue desktop/src/renderer/components/wiki/*.test.ts
git commit -m "feat(workspace): add the accessible wiki tree"
```

### Task 3: 安全 Markdown 阅读、编辑、目录与反向链接

- [ ] **Step 1: 写 XSS、wikilink 与 evidence link 测试**

```typescript
it('removes scripts and preserves vid2note evidence links', () => {
  const html = renderMarkdown('<script>alert(1)</script>[证据](vid2note://source/src_x?start=1&end=2)')
  expect(html).not.toContain('<script')
  expect(html).toContain('data-evidence-source="src_x"')
})
```

- [ ] **Step 2: 实现 MarkdownReader**

markdown-it 关闭 raw HTML；DOMPurify 使用 allowlist；插件转换 `[[path|label]]` 与 `vid2note://source` 为可拦截链接。外部 `http(s)` 链接通过 Electron opener 打开，不能在 WebView 导航。

- [ ] **Step 3: 实现 CodeMirror MarkdownEditor**

进入编辑保存当前 `base_hash`；保存调用 human update；409 conflict 打开 before/current/user 三方提示，不自动覆盖。编辑器支持 Cmd/Ctrl+S、Esc 返回阅读、frontmatter 折叠，不尝试复刻完整 Obsidian 插件系统。

- [ ] **Step 4: 实现 outline/backlinks**

Outline 从渲染 token 生成稳定 heading ids；backlinks 来自 Vault API 扫描结果。宽屏显示右侧辅助面板，窄屏用可打开 drawer。

- [ ] **Step 5: 运行并提交**

Run: `npm --prefix desktop run test:unit -- MarkdownReader MarkdownEditor PageOutline BacklinksPanel && npm --prefix desktop run build`

```bash
git add desktop/src/renderer/components/wiki desktop/src/renderer/views/WikiWorkspace.vue
git commit -m "feat(workspace): add safe wiki reading and editing"
```

### Task 4: 来源证据专注视图

- [ ] **Step 1: 写证据点击和 unavailable 状态测试**

```typescript
it('seeks the player and highlights the matching transcript segment', async () => {
  const wrapper = mount(SourceWorkspace, { props: { source, startMs: 761000, endMs: 808000 } })
  await wrapper.get('[data-segment-id="seg-000142"]').trigger('click')
  expect(wrapper.get('video').element.currentTime).toBeCloseTo(761, 1)
  expect(wrapper.get('[data-segment-id="seg-000142"]').attributes('aria-current')).toBe('true')
})

it('shows transcript fallback when original media is unavailable', () => {
  const wrapper = mount(EvidenceCard, { props: { reference: unavailableReference } })
  expect(wrapper.text()).toContain('仅字幕证据')
  expect(wrapper.find('video').exists()).toBe(false)
})
```

- [ ] **Step 2: 实现 SourcePlayer**

使用 HTML video/audio；接收 signed local media URL 与 start/end；seek 后等待 `seeked` 再更新 UI；end 到达时暂停 clip preview。没有原视频时呈现“仅字幕证据”和重新获取来源动作。

- [ ] **Step 3: 实现章节化 SourceTimeline**

虚拟化长 transcript；当前 segment 有文本标签与 `aria-current`；点击 segment seek；播放器 timeupdate 只更新附近 segment，避免每帧全表扫描。

- [ ] **Step 4: 实现 EvidenceCard**

展示 claim、来源标题、时间范围、frame/clip 状态和证据不足说明；截图是实际 API 资源，不使用 placeholder box 或 CSS 假图。

- [ ] **Step 5: 连接 Markdown evidence links**

普通点击在 SourceWorkspace 打开对应区间；修饰键点击在 Agent 侧栏预览卡；start/end 统一为毫秒。

- [ ] **Step 6: 运行并提交**

Run: `npm --prefix desktop run test:unit -- SourcePlayer SourceTimeline EvidenceCard && npm --prefix desktop run typecheck`

```bash
git add desktop/src/renderer/components/source desktop/src/renderer/views/SourceWorkspace.vue
git commit -m "feat(workspace): add source evidence playback"
```

### Task 5: ChangeSet 多文件 Diff Review

- [ ] **Step 1: 写选择、冲突和审批测试**

```typescript
it('submits only selected operation indexes', async () => {
  const wrapper = mount(DiffReview, { props: { changeset } })
  await wrapper.get('[data-operation-index="1"] input').setValue(false)
  await wrapper.get('[data-testid="approve-selected"]').trigger('click')
  expect(wrapper.emitted('approve')?.[0]).toEqual([[0]])
})

it('blocks apply when validation has errors', () => {
  const wrapper = mount(DiffReview, { props: { changeset: invalidChangeSet } })
  expect(wrapper.get('[data-testid="approve-selected"]').attributes('disabled')).toBeDefined()
})

it('requires an explicit choice for contradictions', async () => {
  const wrapper = mount(ContradictionPanel, { props: { contradiction } })
  await wrapper.get('[data-testid="confirm-contradiction"]').trigger('click')
  expect(wrapper.text()).toContain('请选择处理方式')
})
```

- [ ] **Step 2: 实现 ChangeSetList**

按 pending/applied/rejected/reverted 分组；显示 source、runtime、created time、summary 和 validation count；pending badge 与 WikiTree 使用同一 store。

- [ ] **Step 3: 实现 CodeMirror Merge DiffReview**

每个 operation 独立可选择；create/update/rename 有文本标签；base hash conflict 只允许重新生成/重新基于，不显示可绕过的“强制覆盖”。

- [ ] **Step 4: 实现 ContradictionPanel**

并排显示 claim A/B、各自时间证据、Compiler 建议和用户选择：同时保留、要求修订、拒绝该块。不能以颜色单独区分立场。

- [ ] **Step 5: 实现批准、拒绝、回滚后的状态刷新**

成功后一次刷新 ChangeSet、tree、current page、index 和 log；失败保留选择状态并显示 ErrorEnvelope 的可恢复动作。

- [ ] **Step 6: 运行并提交**

Run: `npm --prefix desktop run test:unit -- ChangeSetList DiffReview ContradictionPanel && npm --prefix desktop run build`

```bash
git add desktop/src/renderer/components/changeset desktop/src/renderer/views/ChangeSetWorkspace.vue
git commit -m "feat(workspace): add changeset diff review"
```

### Task 6: Agent 面板与完整会话视图

- [ ] **Step 1: 写事件渲染和模式一致性测试**

```typescript
it('renders normalized events without runtime-specific branches', () => {
  const wrapper = mount(AgentEventStream, { props: { events: normalizedEvents } })
  expect(wrapper.findAll('[data-agent-event]')).toHaveLength(normalizedEvents.length)
  expect(wrapper.html()).not.toContain('codex-event')
  expect(wrapper.html()).not.toContain('claude-event')
})

it('shows the same autonomy mode in header panel and settings', () => {
  const store = useWorkspaceStore()
  store.autonomyMode = 'approval'
  expect(mount(AgentPanel).text()).toContain('审批模式')
  expect(mount(Settings).text()).toContain('审批模式')
})

it('does not silently switch runtime after failure', async () => {
  const store = useAgentStore()
  store.selectedRuntime = 'codex'
  store.consume(failedRunEvent)
  expect(store.selectedRuntime).toBe('codex')
  expect(store.lastError?.code).toBe('AGENT_PROCESS_FAILED')
})
```

- [ ] **Step 2: 实现 RuntimePicker**

显示 Built-in/Codex/Claude 的 available、version、auth status、capabilities；不可用项禁用并给明确修复说明；切换只影响下一次 run，不中途替换当前 run。

- [ ] **Step 3: 实现 AgentEventStream**

按统一类型分组 thinking 摘要、tool、message、evidence、approval、usage、terminal；未知 payload 显示克制诊断，不崩溃。长 tool output 默认折叠。

- [ ] **Step 4: 实现 AgentComposer**

支持显式附加当前 page、选中文本、source；附件以 chip 展示并可移除；默认不发送整个 Vault。Enter 发送、Shift+Enter 换行、运行中显示 cancel。

- [ ] **Step 5: 实现 write-back handoff**

`changeset.proposed` 显示“审阅变更”，跳转统一 ChangeSetWorkspace；AgentPanel 不自建简化审批按钮。

- [ ] **Step 6: 实现窄屏 drawer 与 Agent 专注视图**

四区首页只显示适合浏览的侧面板；完整会话路由显示 session list、事件、证据和大输入区，共享同一 store/session。

- [ ] **Step 7: 运行并提交**

Run: `npm --prefix desktop run test:unit -- AgentPanel AgentEventStream AgentComposer RuntimePicker && npm --prefix desktop run typecheck`

```bash
git add desktop/src/renderer/components/agent desktop/src/renderer/views/AgentWorkspace.vue desktop/src/renderer/layouts/WorkspaceLayout.vue
git commit -m "feat(workspace): add normalized agent conversations"
```

### Task 7: 导入、媒体工具、健康检查与设置收口

- [ ] **Step 1: 把导入入口升级为 Source ingest**

ImportWorkspace 支持在线视频、本地视频和 SRT；清楚展示是否保留 original/audio/SRT、是否可能发送到云 ASR/LLM、版权责任提示。创建后跳到 task/source 状态，不另建任务系统。

- [ ] **Step 2: 实现 MediaToolsWorkspace**

提供转音频、截图、按时间切片和思维导图入口；所有长任务复用现有 Task rail/SSE；工具轨只保留“媒体工具”一个一级入口。

- [ ] **Step 3: 实现 Wiki health 页面/面板**

显示孤儿页、broken links、缺 citation、矛盾、陈旧 claim 和 index 漂移；“生成修复建议”创建 ChangeSet，不直接写文件。

- [ ] **Step 4: 扩展 Settings**

设置 Vault path、默认 Runtime、模型、自治模式、媒体保留、clip buffer、云数据说明和 CLI diagnostics；密钥只经 Keychain API，不回显完整值。

- [ ] **Step 5: 写恢复体验测试**

模拟 service restart/interrupted task/agent resume missing/media unavailable，断言 UI 呈现真实状态与明确下一步，不把 interrupted 显示 failed/completed。

- [ ] **Step 6: 运行并提交**

Run: `npm --prefix desktop run test:unit -- ImportWorkspace MediaTools Settings && npm --prefix desktop run build`

```bash
git add desktop/src/renderer/views desktop/src/renderer/components desktop/src/renderer/router desktop/src/renderer/stores
git commit -m "feat(workspace): complete import media and recovery flows"
```

### Task 8: 响应式、无障碍、视觉 QA 与最终 E2E

- [ ] **Step 1: 写三个 viewport E2E**

1440px：四区可见；1024px：tree 默认收起但可恢复；820px：Agent 为 drawer 且主阅读区无水平滚动。拖拽后刷新，宽度偏好仍存在。

- [ ] **Step 2: 写键盘与语义 E2E**

用 Tab/Arrow/Enter/Escape 完成 tree 导航、页面打开、Agent drawer、Diff 选择；所有 icon button 通过 role/name 定位；焦点始终可见。

- [ ] **Step 3: 做视觉对照**

在相同 1440×900 viewport 分别截取 `knowledge-workspace-v1` 参考和生产工作台，组合对照暖灰背景、阅读面、azure 使用、边框、字号、pane spacing、focus/selected states。只修正可见差异，不复制模板缺失 CSS/inline scripts。

- [ ] **Step 4: 写知识 MVP E2E**

测试必须驱动真实本地 fixture：导入 source A → 批准 ChangeSet → 导入 source B → 同页增强/矛盾 → Agent 回答 → 播放证据 → 重启 app → 状态保留。Fake LLM/CLI 允许，但 Worker、Vault、ChangeSet、API 和 UI 必须真实。

- [ ] **Step 5: 运行完整门禁**

Run:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy core/src server/src
npm --prefix desktop run contracts:check
npm --prefix desktop run test:unit
npm --prefix desktop run typecheck
npm --prefix desktop run build
npm --prefix desktop run test:e2e -- test_workspace_responsive.spec.js test_workspace_accessibility.spec.js test_knowledge_mvp.spec.js
```

Expected: every command exits 0; MVP E2E verifies real Markdown files and media seek within 2000ms.

- [ ] **Step 6: 验证打包与离线视觉资源**

Run: `npm --prefix desktop run electron:build`

Expected: packaged app starts without network fonts/assets; Vault remains outside application bundle; third-party notices include FFmpeg/yt-dlp and audited ASR obligations.

- [ ] **Step 7: 更新 CodeGraph 并提交**

```bash
codegraph update
git add desktop/src/renderer desktop/tests/e2e desktop/package.json desktop/package-lock.json
git commit -m "test(e2e): verify the complete knowledge workspace"
```
