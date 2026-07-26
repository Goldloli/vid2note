## 1. i18n 框架

- [x] 1.1 `npm install vue-i18n@9`；新建 `i18n.js`（legacy global `$t`）+ `locales/zh.js` + `locales/en.js`（nav/common/status/console/note/mindmap/asr/history/settings/task/pipeline/engine 命名空间）
- [x] 1.2 `main.js` 注册 i18n；`stores/config.js` 加 `locale` + `changeLocale`（i18n.global + localStorage + document.lang）

## 2. 全 UI 文案 i18n

- [x] 2.1 `App.vue`（标题 / 侧栏 nav / 引擎卡 / 页签 / 提示）
- [x] 2.2 `Console.vue`（新建任务 / 上传 / 选择项 / 统计卡 / 进行中 / 最近完成 / 状态文案）
- [x] 2.3 `Note.vue`（标题 / 复制 / 导出 / 思维导图入口 / PDF 对照 / 大纲）
- [x] 2.4 `Mindmap.vue`（标题 / 视图控制 / 大纲 / 导出 / 错误提示）
- [x] 2.5 `Asr.vue`（三引擎说明 / 策略 / external / 测试 / 保存）
- [x] 2.6 `History.vue`（筛选 / 表头 / 批量 / 分页 / 搜索）
- [x] 2.7 `Settings.vue`（各分区 + **语言切换 chip 中/En**）
- [x] 2.8 `TaskDetail.vue`（状态 / Tab / 元数据键 / 日志 / 重跑取消）
- [x] 2.9 `asr.js`（ASR_ENGINES / STRATEGIES 的 l/desc 改 i18n key）+ `PipelineRail.vue`（节点名 pipeline.*）

## 3. 测试与验收

- [x] 3.1 `cd frontend && npm run build` 通过（vue-i18n 进主 chunk，无裸 key）
- [ ] 3.2 docker 重建 + 手动切中/英验证全站文案 + 持久化（**需容器验证**）
- [x] 3.3 `bd` 建任务跟踪
