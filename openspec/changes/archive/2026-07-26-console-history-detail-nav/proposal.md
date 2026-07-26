## Why

主控台 / 历史 / 任务详情三页骨架虽在，但对照 `web-frontend` spec 仍有大量未落地，且后端能力其实早已就绪而前端没用上：

- **Console**：缺本地上传、LLM 引擎选择、输出语言、思维导图开关、PDF 上传、4 张状态统计卡；进行中任务用 3s 轮询而非 SSE。
- **History**：缺状态 / 来源筛选、分页、多选批量导出 / 重跑、失败行重跑——而后端 `list_history(status,source_type,q,page,page_size)` 与 `batch(export/rerun)` 均已支持。
- **TaskDetail**：缺节点产物标签 + 耗时、进度环、跳过节点态、产物 Tab（转录稿 / 笔记预览 / 元数据）。
- **Settings**：LLM / 并发 / PDF / 语言 的 key 映射 bug（下划线 key 存不进，change② 仅修了 ASR 段）。

本 change 以前端落地为主，补一个轻量统计聚合接口，并顺手修 Settings 残留 key 映射。

## What Changes

- **Console**：本地上传（video / audio，后端 `create_task(uploaded)` 已支持）、LLM 引擎单选、输出语言、思维导图开关、PDF 讲义上传、**4 张状态统计卡**（进行中 / 今日完成 / 累计任务 / 累计完成，来自 `GET /tasks/stats`）、进行中任务**近实时短轮询**（2s 替代 3s；全局任务 SSE 广播留后续）。
- **History**：状态 + 来源筛选 chip（带计数）、分页器、行多选批量导出 / 重跑、失败行重跑（全部复用现有后端）。
- **TaskDetail**：节点产物标签（文件名 + 大小）+ 本节点耗时、进度环、跳过节点态、产物 Tab（转录稿 / 笔记预览 / 元数据）。
- **Settings**：修 LLM / 并发 / PDF / 语言 key 映射（`llm.provider` / `concurrency.max` / `pdf.mode` / `note.output_language`），让现有 UI 能正确读写。
- **后端**：新增 `GET /api/v1/tasks/stats` 聚合（进行中数 / 今日完成数 / 累计任务数 / 累计笔记时长）。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `web-frontend`：修订「主控台运行态总览」Requirement，明确四张统计卡的数值 MUST 来自 `GET /tasks/stats` 聚合接口。其余 Console / History / TaskDetail 相关 Requirement 在 main spec 中已存在，本 change 为**实现落地**。

## Impact

- **前端**：`Console.vue` / `History.vue` / `TaskDetail.vue` 大改；`Settings.vue` key 映射修复；`api/index.js` 加 `taskStats()` + 上传走现有 `createTask(FormData)`。
- **后端**：`api/v1/tasks.py` 加 `GET /tasks/stats`；`task_service` 加 `aggregate_stats`（委托 repo 聚合）。
- **测试**：`stats` 单测；`npm run build`。

## Non-goals

- 设置页「八家 LLM 完整凭证展开 UI + 连接测试」—— 本 change 只修 key 映射让现有精简 UI 可用，八家凭证面板留后续。
- 任务详情招牌节点动效（弹簧 / 流光，spec 列为 SHALL）—— 本 change 先补内容与状态，动效 polish 可后续。
- 液态玻璃 —— 项目已转「清晰普通版」（`DESIGN.md`），不改回。
- 笔记 / 导图页内容（change①）、ASR 页（change②）已覆盖，不动。

### 复用 vs 新增边界

- **复用**：`list_history` / `batch` / `rerun` / `create_task(uploaded)` / SSE `streamTask` / `createTask(FormData)` / `DESIGN.md` 组件。
- **新增 / 改造**：`GET /tasks/stats` + `aggregate_stats`；Console / History / TaskDetail 三页 UI；Settings key 映射。
