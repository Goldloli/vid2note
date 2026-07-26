## 1. 笔记浏览页 NotesBrowser.vue

- [x] 1.1 三栏布局（左 240 列表 / 中 flex 正文 / 右 280 Tab）；左栏 `listTasks({status:'completed', q, page_size:100})` + 搜索框（300ms 防抖）+ 时间倒序 + 默认选最新
- [x] 1.2 中栏：选中 id → `fetch getProductUrl(id,'note')` → `marked.parse` → v-html（720px 限宽）
- [x] 1.3 右栏 Tab[大纲 | 操作]：大纲 = 中栏 DOM 抽 h1/h2/h3 TOC（点击 scrollIntoView）；操作 = 导出 .md / 复制 md / →思维导图 / 元信息（源/ASR/LLM）

## 2. 导图浏览页 MindmapsBrowser.vue

- [x] 2.1 三栏布局；左栏同笔记页（completed 列表 + 搜索 + 默认最新）
- [x] 2.2 中栏：选中 id → 动态 import markmap-view 渲染笔记标题层级预览（缩放/折叠）
- [x] 2.3 右栏 Tab[大纲 | 操作]：大纲 = fetch mindmap md 文本大纲；操作 = 导出 xmind/png/md（按 index）/ →笔记 / 元信息

## 3. 路由与侧栏

- [x] 3.1 `router/index.js` 加 `/notes` → NotesBrowser、`/mindmaps` → MindmapsBrowser
- [x] 3.2 `App.vue` 侧栏笔记 / 导图 改 `<router-link to="/notes">` / `to="/mindmaps"`；移除 `goLatest` 与相关 import

## 4. 测试与验收

- [x] 4.1 `cd frontend && npm run build` 通过
- [ ] 4.2 docker 重建 + 手动：侧栏进浏览页 / 列表搜索切换 / 中栏联动 / 大纲定位 / 操作导出跳转（**需容器验证**）
- [x] 4.3 `bd` 建任务跟踪
