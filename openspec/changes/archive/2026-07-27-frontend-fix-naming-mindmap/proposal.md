## Why

两处需修正：
1. **命名**：列表兜底用了视频标识（BV号/videoId），用户要的是**视频内容标题**；且在线视频下载时没把 yt-dlp 取到的视频标题存进 `task.title`（导致 `None`）。
2. **导图预览**：默认只展开 2 层；缺平移按键。

## What Changes

- **后端**：`download_video` 从 yt-dlp `info_dict` 提取视频标题，经 `_download` 节点存入 `task.title`（在线视频获得视频标题）；笔记节点的 AI H1 仍覆盖（AI 标题优先）。
- **前端 `displayName`**：兜底**去掉**视频标识/链接，改为「未命名」（标题优先级：AI H1 → 视频标题清洗 → 未命名）。
- **前端导图**：`initialExpandLevel` 改 `-1`（全部展开）；上方加**平移**按键（上/下/左/右），缩放+平移统一用 CSS `transform: translate() scale()`。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `web-frontend`：修订「列表项统一命名」——兜底用「未命名」，MUST NOT 用视频标识/链接；修订导图预览——默认全部展开 + 提供平移按键。

## Impact

- **后端**：`media_ingest/downloader.py`（progress hook 提 title + `download_video` 暴露）；`runtime/runner.py` `_download` 存 `task.title`。
- **前端**：`format.js`（displayName 兜底）；`Mindmap.vue` + `MindmapsBrowser.vue`（全展开 + 平移按键）。
- **测试**：title 提取单测；`npm run build`。

## Non-goals

- direct 链接 yt-dlp 取不到标题时仍走「未命名」（不强解析 URL）。
- 导图节点编辑（仍是只读）。
