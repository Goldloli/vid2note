## Context

当前 `Note.vue` / `Mindmap.vue` 处于初级状态（见 proposal）。本 change 为**纯前端改造**：后端的笔记产物、PDF 产物、mindmap 三格式导出接口均已存在（`frontend/src/api/index.js` 的 `getProductUrl(id, 'note'|'mindmap'|'pdf')`），前端只需消费。

前端栈：Vue3 + Vite + `marked`，`DESIGN.md` 已沉淀设计 token（玻璃浮卡、动效曲线、衬线/无衬线字体、明暗主题）。约束：导图页禁止交互编辑（`mindmap-export` spec 明令 v1 Non-goal）；本地 Docker 自用，无 SSR / 多用户 / 鉴权顾虑。

## Goals / Non-Goals

**Goals:**

- 笔记页：章节 TOC 定位 + 滚动高亮、PDF 讲义双栏对照、720px 舒适阅读排版。
- 导图页：markmap 只读可视化预览（缩放 / 适应 / 居中 + 节点折叠）、文本大纲面板、沿用 xmind/png/md 导出。
- 复用现有产物接口与 `DESIGN.md` 设计系统，**不引入任何后端改动**。

**Non-Goals:**

- 导图交互编辑（节点增删改 / 连线 / 拖拽）、笔记内联编辑、PDF 双栏同步滚动、新导出格式、其他四页改动。

## Decisions

### D1 导图渲染选 `markmap-lib` + `markmap-view`

- **Why**：markmap 直接以 markdown 标题层级为输入生成树，与 `mindmap-export` spec「以笔记为唯一输入」天然契合；纯 SVG 只读渲染，**本身不提供节点增删改 / 连线编辑**，从结构上保证 Non-goal。
- **Alt**：`jsmind`（需手动建树 + 显式 disable 编辑）、`mind-elixir`（强交互、要关编辑模式）、自行 SVG 绘制（成本高）。均不如 markmap 契合「只读预览」。
- 视图控制用 markmap-view 内置 `setScale` / `fit` / `rescale`；节点点击折叠为其原生能力（`initialExpandLevel` 可控默认展开层级）。缩放百分比读内部 scale 状态同步显示。

### D2 TOC 用 `marked.lexer` 解析标题 + `IntersectionObserver` 高亮

- **Why**：`marked` 已是依赖；用其 token 流解析标题可避开代码块内 `#` 的误判（纯正则会把代码块里的 `#` 当标题）。渲染时给每个标题注入 slug id，TOC 项点击走 `scrollIntoView`，`IntersectionObserver` 监听标题进入视口以高亮当前大纲项。
- **Alt**：正则（误判代码块）、再引 `markdown-it`（重复依赖）。

### D3 PDF 双栏用原生 `<iframe>` 嵌入 PDF 产物

- **Why**：浏览器原生 PDF 渲染够用，零额外依赖。PDF 经本 change 新增的 `products` 路由 `pdf` kind（暴露 `task.pdf_path`）取；仅当任务携带 PDF（`task.pdf_path` 非空）时显示对照开关，不携带时开关隐藏并提示「本任务无讲义 PDF」。
- **Alt**：`pdf.js`（仅在原生渲染异常或日后要做同步滚动时再引入，v1 不做）。

### D4 文本大纲面板复用 `mindmap?format=md` 导出

- **Why**：后端已有 mindmap 的 md 大纲导出，与导图同源（都派生自笔记标题层级），可保证「与导图同构」。前端 `fetch` 该 md 大纲后以缩进纯文本展示，与导图预览并排（宽屏）/ 切换 Tab（窄屏）。

### D5 排版：720px 限宽居中 + 衬线标题 + 行距 1.8 + 16px

复用 `DESIGN.md` 字体 token。单栏时正文 720px 居中、TOC 作侧边目录；开启 PDF 对照时整页切为左右双栏（笔记栏仍内部限宽，PDF 栏自适应）。

### D6 markmap 懒加载

导图页用动态 `import('markmap-view')`，避免 d3 进入主 chunk 拖大首屏体积；笔记页不受影响。

## Risks / Trade-offs

- **[markmap 体积 / 构建]** markmap-view 依赖 d3，增大 bundle → **缓解**：动态 import 懒加载，仅导图页承担；本地自用对体积不敏感。
- **[PDF iframe Content-Type]** 后端产物路由 MUST 返回 `application/pdf` → **缓解**：联调校验响应头；失败时回退为「下载 PDF」链接。
- **[标题解析鲁棒性]** 无标题笔记、代码块内 `#` → **缓解**：用 marked token 而非正则；无标题时 TOC 显示「无章节」空态，不影响正文渲染。
- **[导图大节点性能]** 超长笔记层级深时 SVG 节点多 → **缓解**：`fit` 适应 + `initialExpandLevel` 默认收起深层；自用场景笔记规模有限，暂不做虚拟化。

## Migration Plan

纯前端增量改造，**无数据迁移**。回滚：还原 `Note.vue` / `Mindmap.vue` 两个文件 + `npm uninstall markmap-lib markmap-view` 即可，不影响后端与其它页面。

## Open Questions

- 导图预览与文本大纲默认布局：**建议宽屏并排、窄屏切换 Tab**（design 已定此策略，实现时按断点切）。
- PDF 对照是否同步滚动：v1 **不做**（Non-goal），左右栏各自独立滚动。
