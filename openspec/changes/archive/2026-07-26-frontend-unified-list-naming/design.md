## Context

`_make_executors(task, snapshot, data_root)` 无 repo 参数，`_note` 闭包无法持久化 title。run_task_dag 有 repo（433）。

## Goals / Non-Goals

**Goals:** 列表项统一 `MM-DD 标题·来源`；AI 笔记 H1 覆盖 task.title（新任务生效，持久）。

**Non-Goals:** 存量回填；排序/分组。

## Decisions

### D1 覆盖 task.title（不加新 DB 列）

- **Why**：tasks 表无迁移机制（CREATE IF NOT EXISTS + 无 ALTER），加 `note_title` 列对旧库不生效。`task.title` 列已存在，note 节点用 AI H1 覆盖即可持久，零迁移。
- 副作用：title 显示在 Console/History/TaskDetail/浏览页，统一变 AI 标题（更准），符合用户"AI 标题优先"。

### D2 _make_executors 加 repo 参数

- run_task_dag（433 `repo = repo or TaskRepository()`）传给 `_make_executors(task, snapshot, data_root, repo)`；`_note` 用 `repo.update(task_id, title=h1)`。

### D3 H1 提取 + 清洗

- `re.search(r'^#\s+(.+)$', markdown, re.MULTILINE)` 取首个 H1；`.strip().strip('*`#_>').strip()` 去 markdown 强调符号。空跳过。

### D4 前端 displayName

- `MM-DD`（created_at 或 finished_at）+ 标题（`task.title` 清洗去视频后缀；空→视频标识 BV/id；再空→`source.unnamed`）+ ` · ` + 来源名（source_type → i18n）。
- 三处列表（NotesBrowser/MindmapsBrowser/History）共用。

## Risks / Trade-offs

- **[AI H1 含特殊符号]** → 清洗 strip 常见强调符；极端情况 fallback 原标题。
- **[存量 5 任务无 AI 标题]** → 走 title（文件名/在线 None→兜底）；用户可重跑笔记节点回填。

## Migration Plan

无 DB 迁移。新任务笔记生成时自动覆盖 title。回滚：还原 runner `_note` + `_make_executors` 签名。
