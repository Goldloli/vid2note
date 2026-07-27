## Context

yt-dlp 下载时 progress hook 的 `finished` 状态 `d` 含 `info_dict`（视频标题）。当前 hook 只推进度，未提取 title。

## Goals / Non-Goals

**Goals:** 在线视频获得视频标题存 task.title；displayName 兜底用未命名（非标识）；导图全展开 + 平移按键。

**Non-Goals:** direct 无标题时强解析 URL；导图编辑。

## Decisions

### D1 progress hook 提取 title（经 holder 传出，不改返回值）

- `_make_progress_hook(ctx, title_holder=None)`：finished 时 `info_dict.title` 存 holder；`download_video` 创建 holder、传 hook、末尾 `setattr(ctx, "_video_title", ...)`。
- **不改 download_video 返回值**（仍 rel path），避免破坏调用方/测试；title 经 ctx 属性传出。
- _download 读 `getattr(ctx_ext, "_video_title")`，`repo.update(task_id, title=...)`。

### D2 displayName 兜底 = 未命名

- 标题优先级：`task.title`（被 AI H1 或视频标题覆盖）→ 清洗去视频后缀 → **未命名**（i18n `source.unnamed`）。删除 videoId 兜底。

### D3 导图全展开 + 平移（CSS transform）

- `initialExpandLevel: -1`（markmap 全展开）。
- 缩放 + 平移统一用包裹层 `transform: translate(${tx}px,${ty}px) scale(${s})`；按键：放大/缩小（s ±0.2）、平移上/下/左/右（tx/ty ±60）、居中（reset）、适应（`mm.fit()`）。
- `zoom:false` 禁内置滚轮，全由按键 CSS 控制。

## Risks / Trade-offs

- **[info_dict.title 缺失（direct/受限视频）]** → holder 空 → task.title 不更新 → displayName 走未命名。
- **[CSS transform 平移 vs markmap 内部坐标]** → 禁用 markmap zoom，纯 CSS 控制，简单可控；fit 仍调 `mm.fit()`（内部适配内容）。

## Migration Plan

无 DB 迁移。新任务下载 + 笔记生成后 title 正确。回滚：还原 downloader/runner/format/Mindmap。
