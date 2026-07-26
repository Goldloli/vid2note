## 1. 后端统计接口

- [x] 1.1 `repo.aggregate_stats()`（running/today_completed/total/completed 纯 SQL 聚合）+ `task_service.aggregate_stats()` + `GET /api/v1/tasks/stats` 路由 + `TestStats` 单测

## 2. Console 主控台

- [x] 2.1 本地上传入口（video/audio，走 `createTask(FormData)` + 后端 `create_task(uploaded)`）
- [x] 2.2 LLM 引擎单选 + 输出语言（中/英）+ 截图开关（思维导图开关 / PDF 上传涉及 FormData list 与 PDF 上传路由，留后续）
- [x] 2.3 4 张状态统计卡（`GET /tasks/stats`：进行中 / 今日完成 / 累计任务 / 累计完成）
- [x] 2.4 进行中任务列表 2s 短轮询近实时（替代 3s）

## 3. History 历史页

- [x] 3.1 状态筛选（全部/进行中/已完成/失败，带计数）+ 来源筛选（YouTube/Bilibili/直链/本地视频/本地音频）
- [x] 3.2 分页器（显示 X–Y / 共 Z，首页禁用上一页）
- [x] 3.3 行多选 + 批量导出（zip，fetch blob）+ 批量重跑（`batchTasks`）
- [x] 3.4 失败行重跑（`rerunTask`）

## 4. TaskDetail 任务详情

- [x] 4.1 节点产物标签（顶层产物 basename）+ 本节点耗时（started_at/finished_at 差）
- [x] 4.2 进度环（SVG circle 按 `task.progress`）
- [x] 4.3 跳过节点态（badge 支持 skipped）
- [x] 4.4 产物 Tab（转录稿 fetch srt / 笔记预览 fetch note md + marked / 元数据 task 键值）

## 5. Settings key 映射修复

- [x] 5.1 `llm.provider` / `llm.model` / `concurrency.max` / `pdf.mode` / `note.output_language`（带点 key），apiKey 写入 `llm.credentials`，load 取 `r.settings`（八家凭证面板留后续）

## 6. 测试与验收

- [x] 6.1 `TestStats` 单测 + 后端全量 240 测试绿
- [x] 6.2 `cd frontend && npm run build` 通过
- [x] 6.3 联调：docker 内 `GET /tasks/stats`（running/today/total/completed）验证通过；浏览器 Console 上传 / History 筛选分页批量 / TaskDetail 产物 Tab 交互待用户实测
- [x] 6.4 用 `bd` 建任务跟踪并随实现更新状态
