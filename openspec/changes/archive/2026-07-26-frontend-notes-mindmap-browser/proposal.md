## Why

`frontend-sidenav-notes` 的侧栏「笔记 / 导图」页签只跳「最近一篇」，用户反馈太单薄——独立页签若只跳最近一篇没有存在意义。需要**全量浏览页**：左=所有笔记 / 导图列表（搜索 + 时间倒序），中=选中项内容，右=大纲 / 操作 Tab。

## What Changes

- **新增笔记浏览页 `/notes`**：左（搜索框 + 全量已完成任务列表，按完成时间倒序，默认选中最新一篇）｜中（选中任务的笔记正文，720px marked 渲染）｜右（Tab「大纲」= 章节大纲 TOC 点击定位 / 「操作」= 导出 .md、复制 md、→思维导图、任务元信息）。
- **新增导图浏览页 `/mindmaps`**：左（搜索 + 列表）｜中（选中任务的 markmap 只读预览 + 缩放/折叠）｜右（Tab「大纲」= 文本大纲 / 「操作」= 导出 xmind/png/md、→笔记、元信息）。
- **侧栏「笔记」「思维导图」**由 `goLatest`（最近一篇）改为 `router-link` → `/notes` / `/mindmaps`（进入全量浏览页）。
- 列表项点击切换选中，中栏 + 右栏联动；大纲项点击定位中栏。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `web-frontend`：**新增「笔记 / 导图全量浏览页」Requirement**；修订「应用骨架与导航」——侧栏笔记 / 导图页签进入对应浏览页（左中右三栏），而非只跳最近一篇。

## Impact

- **前端**：新建 `views/NotesBrowser.vue` + `views/MindmapsBrowser.vue`；`router/index.js` +`/notes` `/mindmaps`；`App.vue` 侧栏笔记 / 导图改 `router-link`（去掉 `goLatest`）。复用 `marked`、`markmap`、`listTasks`、`getProductUrl`。
- **spec**：`web-frontend` ADDED 浏览页 + MODIFIED 导航。
- **测试**：`npm run build`；手动点侧栏进浏览页 + 列表切换 + 大纲定位 + 操作。

## Non-goals

- `/note/:id`、`/mindmap/:id` **单篇页保留**（任务详情 / 历史的入口、深链接），浏览页是**新增的全局入口**，不替换单篇页。
- 跨任务全文搜索（本 change 只搜标题 / 链接 / 来源）。
- 笔记 / 导图内容编辑、版本对比。
