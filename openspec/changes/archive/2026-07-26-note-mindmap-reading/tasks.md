## 1. 前置与依赖

- [x] 1.1 在 `frontend/package.json` 加入 `markmap-lib` + `markmap-view` 依赖，`npm install` 后验证 `npm run build` 通过
- [x] 1.2 后端 `products` 路由 (`backend/src/api/v1/tasks.py`) 加 `pdf` kind 暴露 `task.pdf_path`，并加单测；确认 note（纯文本）、mindmap md 大纲（`getProductUrl(id,'mindmap')` 按 `index` 取）接口与 Content-Type

## 2. 笔记页 Note.vue

- [x] 2.1 用 `marked.lexer`/渲染后 DOM 抽 `h1/h2/h3` 生成 TOC（marked 已隔离代码块内 `#`）；无标题时大纲区隐藏
- [x] 2.2 渲染时为每个标题注入 slug id；TOC 项点击走 `scrollIntoView` 平滑定位
- [x] 2.3 用 `IntersectionObserver` 监听标题进入视口，在大纲中高亮当前章节（单选高亮）
- [x] 2.4 舒适阅读排版：正文限宽 720px 居中、标题衬线、正文行距 1.8、字号 16px、代码块/引用用 `.card` 承载（复用 `DESIGN.md` token 与全局 `.note-md`）
- [x] 2.5 PDF 讲义双栏对照开关：任务携带 PDF（`task.pdf_path`）时显示，开启切为左笔记 / 右 PDF（`<iframe>`，后端 inline 返回）双栏，关闭恢复单栏 + TOC；无 PDF 时提示「本任务无讲义 PDF」

## 3. 思维导图页 Mindmap.vue

- [x] 3.1 动态 `import('markmap-view')`，把笔记标题层级渲染为 SVG 只读预览（`zoom:false` 禁滚轮，无编辑入口）
- [x] 3.2 视图控制条：放大 / 缩小（CSS scale 0.4–2）/ 适应（`mm.fit()`）/ 居中（`mm.rescale()`），缩放百分比同步显示
- [x] 3.3 节点点击折叠 / 展开子树（markmap 原生，`initialExpandLevel=2`）；折叠不改变导出内容
- [x] 3.4 文本大纲面板：优先 `fetch` mindmap md（按 `index`），无 md 格式则从笔记标题兜底解析；分栏 / 仅导图 / 仅大纲 三种视图
- [x] 3.5 沿用 xmind / png / md 三格式导出，改用 `?index=`（按 `mindmap_formats` 顺序映射）替代失效的 `?format=`，三种格式可分别下载

## 4. 测试与验收

- [x] 4.1 后端 `test_download_pdf_inline` 单测（pdf kind 200 + application/pdf + 不带 attachment）；前端无 Vitest，以 build + 手动步骤替代
- [x] 4.2 `cd frontend && npm run build` 构建通过（822 模块，markmap 懒加载独立 chunk，未污染主包）；后端 235 测试全绿
- [x] 4.3 联调：docker 重建 + API 验证通过（health / settings / asr status·test / tasks.stats / 前端同源托管）；浏览器深度交互（TOC 定位 / 导图折叠 / PDF 对照）待用户实测
- [x] 4.4 用 `bd` 建任务跟踪（vid2note-zhr 笔记 / v84 导图 / e1g 验收），随实现更新状态
