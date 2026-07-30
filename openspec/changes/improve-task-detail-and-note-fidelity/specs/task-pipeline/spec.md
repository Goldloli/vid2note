## ADDED Requirements

### Requirement: SSE 日志消息字段与前端消费契约

每个 `log` SSE 事件 MUST 在 `payload.line` 中携带非空的用户可读日志文本，并在 `payload.level` 中携带 `info`、`ok`、`warn` 或 `error` 之一。前端 MUST 优先消费 `payload.line`，同时 MAY 兼容历史 `payload.message` / `payload.msg` 字段；收到空文本日志时 MUST NOT 添加空白活动项。节点进度事件如携带 `payload.message`，前端 MUST 将其作为当前节点的可读活动描述。

#### Scenario: emit_log 产生可显示的事件
- **WHEN** 节点调用 `emit_log("ok", "笔记已落盘")`
- **THEN** SSE `log` 事件 MUST 包含 `payload.level = "ok"` 与 `payload.line = "笔记已落盘"`，任务详情 MUST 增量显示该文本

#### Scenario: 空日志不污染活动时间线
- **WHEN** 前端收到一个缺少 `line`、`message` 与 `msg` 或三者均为空的 `log` 事件
- **THEN** 前端 MUST 忽略该事件，MUST NOT 渲染只有时间戳的空白行

### Requirement: 任务节点快照可恢复基础活动

任务详情在连接实时事件之前 MUST 使用任务详情响应中的 `node_statuses` 恢复已开始、已完成、已失败和已跳过节点的基础活动记录。恢复记录 MUST 使用持久化的 `started_at` / `finished_at` 时间并保持节点顺序；该恢复不要求持久化历史逐行日志。

#### Scenario: 中途打开运行中任务
- **WHEN** 用户在音频节点已完成、转录节点运行中时首次打开任务详情
- **THEN** 页面 MUST 立即显示音频已完成和转录正在进行的基础活动，MUST NOT 因为尚未收到新的 `log` 事件而显示全空日志区

#### Scenario: 容器重启后查看终态任务
- **WHEN** 容器重启后用户打开一个已完成任务，进程内 SSE 历史已经丢失
- **THEN** 页面 MUST 从持久化节点快照恢复各节点的完成活动，并将任务终态显示为已完成

### Requirement: 超详细笔记生成阶段可观测

当 `exhaustive` 长字幕执行分层理解与审校时，笔记节点 MUST 通过现有节点进度和 SSE 机制报告真实阶段，包括理解字幕、构建知识结构、逐章撰写和逐章质量审校。阶段消息 MUST 面向普通用户，MUST NOT 只显示内部方法名或无意义的统一百分比。

#### Scenario: 分段理解进度
- **WHEN** 系统正在理解第 `n` 个、总计 `N` 个 source chunk
- **THEN** 笔记节点 MUST 显示“正在理解字幕第 n/N 段”并持续更新节点进度

#### Scenario: 全局写作与审校进度
- **WHEN** 语义证据提取完成并依次进入全局蓝图、逐章初稿和逐章编辑审校
- **THEN** 笔记节点 MUST 分别显示“正在构建课程知识结构”“正在撰写第 n/N 章”和“正在审校第 n/N 章”
