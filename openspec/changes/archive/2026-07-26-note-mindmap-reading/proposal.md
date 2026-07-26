## Why

笔记页与思维导图页是用户消费产物（笔记 + 导图）的核心入口，但当前均未达到 `web-frontend` spec：

- `Note.vue` 仅用 marked 渲染 markdown，缺章节大纲、PDF 讲义对照与舒适排版，长笔记阅读体验差；
- `Mindmap.vue` 仅三个下载按钮，**完全没有导图可视化预览**，用户无法在下载前看到导图长什么样。

这两页是 v1 可用性最直接的短板，现在补齐。

## What Changes

- **笔记页 `Note.vue`**
  - 新增**章节大纲 TOC**：从笔记 `#`/`##`/`###` 标题自动生成可点击大纲，点击滚动定位到对应章节，正文滚动时在大纲中高亮当前章节。
  - 新增 **PDF 讲义双栏对照**开关：左栏视频笔记 / 右栏 PDF 讲义，关闭恢复单栏（仅当任务携带 PDF 时可用）。
  - **舒适阅读排版**：正文限宽 720px 居中、标题衬线字体、正文行距 1.8、正文字号 16px、代码块/引用用浮卡承载。
- **思维导图页 `Mindmap.vue`**
  - 新增 **markmap 只读可视化预览**：把笔记标题层级渲染为导图，支持放大 / 缩小 / 适应 / 居中，缩放百分比同步显示；支持节点点击**折叠 / 展开**。
  - 新增**文本大纲面板**：与导图同构的缩进文本大纲，与导图预览并排或切换展示。
  - 沿用现有 **xmind / png / md** 三种导出，不新增导出格式。
- **边界**：不改后端 `mindmap-export` / `note-generation`；不改 Console / History / TaskDetail / Settings / ASR（那些在 change ②③）。

## Capabilities

### New Capabilities

（无 —— 本 change 不引入新 capability。）

### Modified Capabilities

- `web-frontend`：思维导图页「思维导图页导出」Requirement 补充「节点折叠 / 展开」只读交互 Scenario（现有 spec 仅覆盖缩放 / 适应 / 居中）。笔记页的 TOC 定位、PDF 双栏对照、舒适排版的 Scenario 在现有 spec 中已存在，本 change 为**实现落地**，spec 文字不变。

## Impact

- **前端代码**
  - 改 `frontend/src/views/Note.vue`（TOC 解析与滚动高亮 + PDF 双栏对照 + 排版样式）。
  - 改 `frontend/src/views/Mindmap.vue`（markmap 预览 + 文本大纲面板 + 视图控制 + 折叠交互）。
  - 新增前端依赖：`markmap-lib` + `markmap-view`（SVG 只读渲染，无画布编辑能力，符合 spec 禁止交互编辑的约束）。
  - 复用 `frontend/src/api/index.js` 现有 `getProductUrl(id, 'note'|'mindmap')`；PDF 经新增的 `pdf` kind 取。
- **后端**：新增最小路由补丁——`products` 路由 (`GET /tasks/{id}/products/{kind}`) 加 `pdf` kind 暴露 `task.pdf_path`（PDF 讲义目前无下载路由，笔记页 PDF 双栏对照依赖它）；笔记 / mindmap 产物接口均已存在。
- **spec**：`web-frontend` delta（思维导图页 +1 Scenario：节点折叠/展开）。
- **测试**：前端组件 / 交互单测（TOC 解析、滚动高亮、导图折叠、PDF 对照布局切换）；PDF 双栏对照依赖任务携带 PDF 产物。

## Non-goals

- 交互式思维导图编辑（节点增删改、连线编辑、拖拽）—— `mindmap-export` spec 明令 v1 禁止，本 change 的「折叠/展开」属于只读视图控制，不越界。
- 后端导出格式扩展（svg / pdf / mm 等）—— spec 限定 xmind / png / md。
- 笔记页内联编辑、笔记版本对比。
- 主控台 / 历史 / 任务详情 / 设置 / ASR 页的任何改动（归属 change ②③）。

### 复用 vs 新增边界

- **复用（不动）**：后端 note 产物接口、mindmap 多格式产物（`mindmap_formats` → `mindmap_paths` 列表，前端改用 `index` 选取格式）、`marked` 渲染、`DESIGN.md` 设计系统（**实色卡片 `.card`**、字体 token）。
- **新增 / 改造**：`Note.vue` / `Mindmap.vue` 的 UI 与交互逻辑、`markmap` 依赖、TOC 解析与滚动高亮、PDF 双栏布局、导图视图控制与折叠、后端 `products` 路由 `pdf` kind（最小补丁，~5 行）。
