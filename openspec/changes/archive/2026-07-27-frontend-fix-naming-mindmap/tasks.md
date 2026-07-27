## 1. 后端:视频标题存 task.title

- [x] 1.1 `media_ingest/downloader.py`:`_make_progress_hook(ctx, title_holder=None)` finished 提 `info_dict.title`;`download_video` 创建 holder、两处 hook 传 holder、末尾 `setattr(ctx,"_video_title",title)`
- [x] 1.2 `runtime/runner.py` `_download`:读 `getattr(ctx_ext,"_video_title")` → `repo.update(task_id,title=...)` + `task.title=...`

## 2. 前端:命名兜底 + 导图控制

- [x] 2.1 `format.js` `displayName` 删除 videoId 兜底 → 「未命名」(i18n `source.unnamed`)
- [x] 2.2 `Mindmap.vue` + `MindmapsBrowser.vue`:`initialExpandLevel:-1`(全展开);加平移按键(↑↓←→),缩放+平移统一 `transform: translate() scale()`

## 3. 测试与验收

- [x] 3.1 后端 240 测试绿;`npm run build` 通过
- [ ] 3.2 docker 重建 + 验证(在线视频标题/AI 标题;导图全展开 + 平移按键,**需容器**)
- [x] 3.3 `bd` 建任务跟踪
