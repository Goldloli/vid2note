## Why

列表项（NotesBrowser / MindmapsBrowser / History）命名不统一：本地上传的标题带 `.mp4` 后缀；在线视频 `title=None` 时直接显示整条长 URL。需统一为 **`MM-DD 标题 · 来源`**，标题优先 AI 笔记 H1。

## What Changes

- **后端**：`_note` 节点笔记落盘后，提取首个 `# H1`（清洗 markdown 符号）覆盖 `task.title` 并 `repo.update` 持久化；`_make_executors` 增加 `repo` 参数透传。
- **前端**：新增 `src/format.js` 的 `displayName(task)` = `MM-DD 标题 · 来源`，标题优先级 `task.title（已被 AI H1 覆盖）→ 清洗去视频后缀 → 视频标识（BV号/videoId）→ 未命名`；`NotesBrowser` / `MindmapsBrowser` / `History` 列表项改用 `displayName`。
- **locale**：加 `source.{youtube,bilibili,direct,localVideo,localAudio,unnamed}` 命名空间。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `web-frontend`：**新增「列表项统一命名」Requirement**（MM-DD 标题 · 来源规则）。

## Impact

- **后端**：`runtime/runner.py`（`_make_executors` 签名 + 调用点 + `_note` 提取 H1）。
- **前端**：新建 `src/format.js`；`locales/zh.js` + `en.js` 加 `source.*`；`NotesBrowser` / `MindmapsBrowser` / `History` 用 `displayName`。
- **测试**：后端单测（H1 提取）；`npm run build`。

## Non-goals

- 回填存量任务的 AI 标题（5 个已完成任务 `title` 已定；新任务笔记生成时自动覆盖。存量若想要 AI 标题需重跑笔记节点）。
- 列表项的排序 / 分组（本 change 只统一命名格式）。
