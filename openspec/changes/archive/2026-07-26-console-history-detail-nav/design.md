## Context

三页骨架已在，后端 `list_history(status,source_type,q,page,page_size)` / `batch(export/rerun)` / `rerun(from_node)` / `create_task(uploaded)` / per-task `streamTask` 均已就绪，但前端 Console / History / TaskDetail 几乎没用上（History 只用 q+page1/size50；Console 无上传、无统计、3s 轮询；TaskDetail 无产物 Tab / 进度环 / 节点耗时）。Settings 的 LLM/并发/PDF/语言 key 映射也存不进（change② 仅修 ASR）。本 change 以前端落地为主，补一个纯 DB 聚合的 `GET /tasks/stats`，并修 Settings 残留 key。

## Goals / Non-Goals

**Goals:** Console 上传 + 引擎/语言/导图/PDF 选择 + 4 统计卡 + 近实时轮询；History 筛选+分页+批量+失败重跑；TaskDetail 节点耗时+产物标签+进度环+产物 Tab；Settings key 映射修复；`GET /tasks/stats`。

**Non-Goals:** 八家 LLM 完整凭证面板 + 连接测试（留后续）；任务详情招牌节点动效（弹簧/流光，留 polish）；全局任务列表 SSE 广播（v1 用短轮询近实时，留后续）；液态玻璃（项目已转清晰普通版）。

## Decisions

### D1 `GET /tasks/stats` 纯 DB 聚合（无文件 IO，秒回）

返回 `{running, today_completed, total, completed}`。`running` = status∈{pending,running} 计数；`today_completed` = 今日 finished_at 计数；`total` = 全部任务计数；`completed` = 已完成计数。「累计笔记时长」v1 用「累计完成」近似（精确音频时长需解析每个产物文件，留后续）。委托 `repo` 加一个聚合查询。

### D2 Console 上传走现有 `createTask(FormData)`

前端 `<input type=file>` 选 video/audio → `FormData` append `file + asr_engine + llm_provider + ...` → `createTask`（后端 `create_task(uploaded)` 已落盘 + 登记 video/audio_path + 跳过对应节点）。

### D3 Console 近实时 = 2s 短轮询

进行中列表 + 统计卡用 2s `setInterval` 刷新（现状 3s）。不引入全局 SSE（后端只有 per-task stream，全局广播属新接口，留后续）。

### D4 History 全复用现有后端

`listTasks({status, source_type, q, page, page_size})`（已支持）+ `batchTasks(ids, 'export'|'rerun')`（已支持）+ `rerunTask(id)`（失败行）。状态/来源 chip 带计数用 listTasks 各筛选 total。

### D5 TaskDetail 产物 Tab + 进度环 + 节点耗时

- 产物 Tab：转录稿（fetch srt）/ 笔记预览（fetch note md + marked）/ 元数据（task 字段键值）。
- 进度环：SVG circle 按 `task.progress` 绘制。
- 节点耗时：`node_statuses[node]` 的 `started_at/finished_at` 差值；产物标签取该节点对应顶层产物（download/note/mindmap → srt/note/mindmap）的文件名 + 大小（`GET /tasks/{id}/products/{kind}` HEAD 或 task 字段）。

### D6 Settings key 映射修复

`llm_provider/llm_model/concurrency/pdf_mode/output_language` → `llm.provider/llm.model/concurrency.max/pdf.mode/note.output_language`（带点 key，后端认）。八家凭证面板留后续。

## Risks / Trade-offs

- **[「累计笔记时长」用「累计完成」近似]** → 偏离 spec 字面，但避免 N 次文件解析；design 已注明，精确时长留后续。
- **[全局 SSE 缺失]** → 主控台用 2s 轮询近实时，自用场景可接受；spec 的「随 SSE」收窄并在 spec delta 注明。
- **[Settings 八家凭证未做]** → 本 change 只修 key 映射让精简 UI 可用，完整凭证面板留后续 change。

## Migration Plan

前端增量 + 后端新增 `GET /tasks/stats`，无数据迁移。回滚：还原三页 vue + 移除 stats 路由。
