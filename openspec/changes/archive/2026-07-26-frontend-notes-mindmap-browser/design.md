## Context

侧栏页签升级为全量浏览页。中栏渲染复用 Note/Mindmap 已有能力（marked / markmap），右栏复用 TOC / 文本大纲 / 导出。

## Goals / Non-Goals

**Goals:** 笔记/导图全量浏览页（左搜索+列表、中内容、右大纲/操作 Tab）；侧栏进浏览页；列表切换联动。

**Non-Goals:** 替换单篇页；全文搜索；内容编辑。

## Decisions

### D1 三栏 CSS flex 布局（左 240px / 中 flex / 右 280px）

- 左栏固定窄宽列表；中栏 flex 占主；右栏固定。窄屏可后续收起左/右栏（v1 不做响应式收起）。

### D2 左列表 = `listTasks({status:'completed', source_type, q, page, page_size})`

- 复用现有 list 接口，筛 `completed`（只有完成的有笔记/导图），按 finished_at/created_at 倒序（接口已按 created_at DESC）。
- 顶部搜索框 `q`（标题/链接/来源），300ms 防抖。
- 默认选中第一篇（最新）；选中态高亮。

### D3 中栏复用渲染

- 笔记：`fetch getProductUrl(id,'note')` → `marked.parse` → v-html；720px 限宽。
- 导图：动态 `import('markmap-view')` 渲染笔记标题层级（同 Mindmap.vue）。
- 选中 id 变化时重新 fetch + 渲染。

### D4 右栏 Tab[大纲 | 操作]

- **大纲 Tab**：笔记页从中栏 DOM 抽 `h1/h2/h3` 建 TOC（点击 `scrollIntoView`，同 Note.vue）；导图页 fetch mindmap md 文本大纲。
- **操作 Tab**：导出（`<a download>` 指向 products）、复制 md、跳转另一页（`router.push`）、任务元信息（源/ASR/LLM/时长占位）。
- Tab 状态 per-page（默认大纲）。

### D5 侧栏改 router-link

- `App.vue` 笔记/导图 `<a @click goLatest>` → `<router-link to="/notes">` / `to="/mindmaps"`，激活态高亮（path 前缀匹配）。移除 `goLatest`。

## Risks / Trade-offs

- **[三栏在窄屏拥挤]** → v1 固定三栏，窄屏收起留后续。
- **[列表 + 中 + 右同时 fetch 多]** → 仅在选中 id 变化时 fetch，切列表无抖动（中栏保留旧内容直到新内容到）。

## Migration Plan

前端增量，无数据迁移。回滚：移除两浏览页 + router + 还原 App.vue 侧栏 goLatest。
