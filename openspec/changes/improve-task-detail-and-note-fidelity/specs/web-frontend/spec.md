## ADDED Requirements

### Requirement: 面向普通用户的任务详情活动视图

任务详情页 MUST 以普通用户可理解的方式呈现当前步骤、整体进度、下一步、六节点状态、产物就绪情况和活动时间线。活动时间线 MUST 使用业务步骤名称与可读描述，不得要求用户理解原始 SSE 事件名、磁盘路径或终端日志；任务 ID、模型、路径和错误原文等技术信息 SHALL 保留在任务参数或展开区域中。桌面、窄屏、明暗主题与减少动画模式下均 MUST 可读。

#### Scenario: 转录中的任务给出当前与下一步
- **WHEN** 任务的转录节点为 `running`，笔记节点为 `pending`
- **THEN** 页面 MUST 明确显示当前正在把音频转成文字，并说明下一步将整理笔记；转录稿与笔记产物 MUST 标记为尚未就绪

#### Scenario: 已完成任务显示可访问产物
- **WHEN** 任务已经完成且登记了 SRT、笔记、截图和导图产物
- **THEN** 页面 MUST 显示已完成状态、可打开的笔记 / 导图操作、可阅读的转录与笔记预览，以及由节点快照恢复的完成活动

### Requirement: 任务产物就绪门禁与正文响应防护

任务详情 MUST 仅在任务记录已登记对应路径后请求转录稿或笔记。产物读取函数 MUST 校验 HTTP 状态、响应类型与正文特征；`text/html`、JSON 错误响应或以 HTML 文档特征开头的内容 MUST NOT 作为 SRT / Markdown 渲染。未登记或 404 MUST 显示“尚未生成或已清理”的明确空态，其他加载失败 MUST 提供可重试错误态。

#### Scenario: 转录节点运行中不请求未就绪 SRT
- **WHEN** `task.srt_path` 为空且转录节点仍在运行
- **THEN** 转录稿 Tab MUST 显示正在生成的空态，MUST NOT 请求或显示 SPA HTML

#### Scenario: 服务返回 HTML 回退页
- **WHEN** 产物请求意外返回 HTTP 200、`Content-Type: text/html` 和应用入口 HTML
- **THEN** 前端 MUST 拒绝将其显示为产物，并呈现可理解的产物不可用状态

#### Scenario: 产物被保留策略清理
- **WHEN** 任务记录曾登记产物但产品端点返回 404
- **THEN** 页面 MUST 说明产物尚未生成或已被清理，MUST NOT 显示原始 JSON 错误正文

### Requirement: 笔记截图通过同源产品 URL 渲染

单篇笔记页、笔记全量浏览页和任务详情笔记预览 MUST 在渲染 Markdown 前，将属于当前任务且已登记的相对截图引用映射到 `/api/v1/tasks/{task_id}/products/screenshot?index={n}`。映射 MUST 基于当前任务的 `screenshot_paths`，MUST NOT 直接把任意磁盘相对路径或 `DATA_ROOT` 路径放入 DOM。历史含 `..` 的路径与新规范路径均 MUST 兼容。

#### Scenario: 打开包含四张截图的历史笔记
- **WHEN** Markdown 含四个 `../../screenshots/<task_id>/shot_<秒>.png` 引用，且任务登记了对应四个截图路径
- **THEN** 页面 MUST 生成四个当前任务产品 URL 并成功显示图片，MUST NOT 请求不存在的 `/screenshots/...` 静态地址

#### Scenario: 未登记的本地相对图片不越权映射
- **WHEN** Markdown 含一个未出现在当前任务 `screenshot_paths` 的本地相对图片引用
- **THEN** 前端 MUST NOT 将其映射到其他任务或任意文件索引

#### Scenario: 笔记复制与导出保持源 Markdown
- **WHEN** 页面已把截图链接改写为同源 URL 供显示，用户点击复制 Markdown 或导出 `.md`
- **THEN** 复制和下载 MUST 继续使用后端存储的原始 Markdown，MUST NOT 把仅用于显示的 API URL 回写到源文件
