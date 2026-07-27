## MODIFIED Requirements

### Requirement: 列表项统一命名

凡展示任务列表的页面（笔记浏览页 / 思维导图浏览页 / 历史页）MUST 以统一格式命名每个列表项：`MM-DD 标题 · 来源`。其中标题 MUST 优先取笔记首个 H1（由后端笔记生成节点提取并持久化到任务标题），其次 MUST 取下载时获得的视频标题（由后端下载节点从 yt-dlp 提取并持久化），再次 MUST 清洗视频标题 / 上传文件名（去除 `.mp4` 等视频后缀）；以上均缺失时 MUST 显示「未命名」，MUST NOT 使用视频标识（BV号 / videoId）或原始长 URL 作为标题。来源 MUST 为可读的来源名（YouTube / Bilibili / 直链 / 本地视频 / 本地音频）。

#### Scenario: 本地文件去后缀命名

- **WHEN** 列表渲染一个本地上传任务（标题为 `讲座.mp4`）
- **THEN** 该项 MUST 显示为 `MM-DD 讲座 · 本地视频`（去除 `.mp4` 后缀），MUST NOT 显示 `.mp4`

#### Scenario: 在线视频用 AI 标题

- **WHEN** 一个在线视频任务完成下载（yt-dlp 取到视频标题）与笔记生成（笔记 H1）
- **THEN** 该任务标题 MUST 被更新为视频标题（下载时）并被 AI H1 覆盖（笔记生成时），列表项 MUST 显示为 `MM-DD <标题> · <来源>`，MUST NOT 显示原始长 URL

#### Scenario: 无标题无 AI 时用视频标识兜底

- **WHEN** 一个任务的标题、视频标题与笔记 H1 均缺失
- **THEN** 列表项 MUST 显示「未命名」作为标题位（如 `MM-DD 未命名 · 直链`），MUST NOT 使用 BV号 / videoId / 长URL 兜底
