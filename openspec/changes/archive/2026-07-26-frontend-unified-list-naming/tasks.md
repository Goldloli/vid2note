## 1. 后端:笔记 H1 覆盖 title

- [x] 1.1 `_make_executors` 签名加 `repo` 参数;调用点传 `repo`(并修 3 处测试 mock)
- [x] 1.2 `_note` 笔记落盘后提取首个 `# H1`(清洗 markdown 符号)→ `repo.update(task_id, title=h1)` + `task.title=h1`;空跳过(H1 提取逻辑由 test_runtime 笔记节点路径集成覆盖,240 测试绿)

## 2. 前端:displayName 统一命名

- [x] 2.1 新建 `src/format.js`:`displayName(task)` = `MM-DD 标题·来源`(title 清洗去视频后缀→视频标识→未命名;来源 source_type 映射 i18n)
- [x] 2.2 `locales/zh.js`+`en.js` 加 `source.{youtube,bilibili,direct,localVideo,localAudio,unnamed}`
- [x] 2.3 `NotesBrowser` / `MindmapsBrowser` / `History` 列表项改用 `displayName(t)`

## 3. 测试与验收

- [x] 3.1 后端全量 240 测试绿;`npm run build` 通过
- [ ] 3.2 docker 重建 + 列表命名验证(本地去后缀 / 在线 AI 标题或标识兜底,**需容器**)
- [x] 3.3 `bd` 建任务跟踪
