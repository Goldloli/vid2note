# web-frontend Specification

## Purpose
定义本地 Web 应用的导航、任务管理、笔记、导图、ASR 和设置交互。确保桌面与窄屏环境下的状态反馈、可访问性和配置编辑保持清晰一致。
## Requirements
### Requirement: 应用骨架与六页导航

前端 MUST 以浏览器访问 `localhost:8761` 的 Web 应用形态提供（由 FastAPI 后端直接托管静态资源，MUST NOT 依赖 Electron 客户端），并 MUST 包含与高保真原型对齐的统一应用骨架：顶部标题栏、左侧固定侧栏、右侧主内容区。侧栏 MUST 提供全局导航入口，至少包含：主控台、笔记、思维导图、历史、ASR、设置；其中「笔记」「思维导图」页签点击后 MUST 进入对应的全量浏览页（`/notes` / `/mindmaps`），并默认定位到最新一篇；任务详情页由主控台 / 历史进入（per-task，不在全局侧栏）。当前所在页 MUST 在侧栏中被高亮为激活态。侧栏底部 MUST 始终展示一份引擎状态卡，实时反映当前选定的 ASR 引擎、LLM 引擎与后端运行态。

#### Scenario: 六页均可通过侧栏到达且布局对齐原型

- **WHEN** 用户在浏览器中打开 `localhost:8761` 并依次点击侧栏的导航项
- **THEN** 应用 MUST 分别渲染主控台、笔记浏览页、思维导图浏览页、历史、ASR、设置各页面，每页的主结构（标题栏 + 侧栏 + 主内容区）MUST 与原型布局一致

#### Scenario: 笔记与思维导图页签定位最近一篇

- **WHEN** 用户点击侧栏「笔记」（或「思维导图」）页签
- **THEN** 应用 MUST 导航到笔记浏览页 `/notes`（或导图浏览页 `/mindmaps`），左栏 MUST 默认选中并展示最新一篇已完成任务的内容

#### Scenario: 当前页在侧栏高亮

- **WHEN** 用户处于任一固定路由页面（例如「ASR」）
- **THEN** 侧栏中该导航项 MUST 被标记为激活态（与其他项有可区分的视觉样式），且其余项 MUST NOT 同时处于激活态

#### Scenario: 侧栏引擎状态卡反映当前配置与后端运行态

- **WHEN** 用户在 ASR / 设置页切换了默认 ASR 或 LLM 引擎，或后端运行态发生变化
- **THEN** 侧栏底部引擎状态卡 MUST 显示最新的 ASR 引擎名、LLM 引擎名与后端运行态（运行中 / 异常），MUST NOT 显示过期值

#### Scenario: 前端为浏览器 Web 应用而非 Electron

- **WHEN** 用户在设置「关于」区域查看运行模式
- **THEN** 页面 MUST 显示其为 Docker 部署的 Web 应用（服务地址 `http://localhost:8761`），MUST NOT 出现「electron」「桌面客户端」等与 v1 形态不符的标识

### Requirement: 主控台任务创建入口

主控台 MUST 提供统一的「新建任务」区，其中网络视频与本地文件 MUST 以**两个并列、同等重要**的区域呈现：网络视频区提供链接输入框（YouTube / Bilibili / 直链），本地文件区提供视频 / 音频文件选择。引擎选择（ASR / LLM / 输出语言 / 截图 / 思维导图）MUST 位于两区下方共享。用户选择本地文件后 MUST NOT 自动开始任务，MUST 由用户手动点击「开始」才提交；点击「开始」时 MUST 按已填写的内容提交（链接非空用链接，否则用已选文件），二者皆空时 MUST 提示且不提交。

#### Scenario: 粘贴链接并选择引擎后提交创建任务

- **WHEN** 用户在网络视频区粘贴一条 `https://www.youtube.com/watch?v=...` 链接，选定 ASR 与 LLM 引擎，点击「开始」
- **THEN** 前端 MUST 调用后端任务创建接口提交该链接与所选引擎，创建成功后该任务 MUST 出现在进行中列表，输入框 MUST 被清空

#### Scenario: 上传本地视频或音频作为输入

- **WHEN** 用户在本地文件区点击「选择文件」并选择一个本地 `.mp4` 或 `.mp3` 文件
- **THEN** 该文件 MUST 被暂存并显示文件名，MUST NOT 自动创建任务或开始；用户随后点击「开始」时前端 MUST 将该文件作为任务输入上传，任务 MUST 出现在进行中列表

#### Scenario: 引擎选择为单选且随设置默认值预填

- **WHEN** 用户首次打开主控台新建任务区
- **THEN** ASR 引擎组与 LLM 引擎组各自 MUST 有且仅有一个被选中（单选），其默认选中项 MUST 取自设置页配置的默认引擎（LLM 默认 DeepSeek `deepseek-v4-flash`）；用户点击同组另一项时 MUST 切换选中并取消原选中

#### Scenario: 未填写任何来源时点开始被拒

- **WHEN** 链接为空且未选择本地文件，用户点击「开始」
- **THEN** 前端 MUST 拒绝提交并提示用户填写链接或选择文件，MUST NOT 调用后端创建接口

#### Scenario: 创建时指定输出语言与思维导图开关

- **WHEN** 用户将输出语言切到「En」并提交
- **THEN** 提交的任务参数 MUST 携带输出语言为英文，MUST NOT 受设置页全局输出语言的覆盖

#### Scenario: 创建时附带 PDF 讲义对照

- **WHEN** 用户在新建任务区点击「PDF 讲义对照」并提交一个 PDF 文件后开始任务
- **THEN** 提交的任务参数 MUST 标记本次任务为 PDF 对照模式，后续笔记页 MUST 能加载该 PDF 与笔记对照

### Requirement: 主控台运行态总览

主控台 MUST 展示运行态总览，包括：状态摘要卡（进行中任务数、今日完成数、累计任务数、累计完成数）、进行中任务列表（每条带六节点流水线轨道、百分比与预计剩余耗时，且随近实时刷新）、最近完成任务表格（提供笔记 / 思维导图 / SRT 等产物入口）。四张统计卡的数值 MUST 来自后端聚合接口 `GET /api/v1/tasks/stats` 而非前端硬编码。进行中任务列表 v1 用短轮询近实时刷新（全局任务 SSE 广播留后续版本）。

#### Scenario: 状态摘要卡展示四项统计

- **WHEN** 用户打开主控台
- **THEN** 页面 MUST 展示进行中任务数、今日完成数、累计任务数、累计完成数四张统计卡，且数值 MUST 来自 `GET /api/v1/tasks/stats` 聚合接口而非前端硬编码

#### Scenario: 进行中任务卡随 SSE 实时刷新

- **WHEN** 存在运行中任务且用户停留在主控台
- **THEN** 每张进行中任务卡 MUST 展示六节点流水线轨道（下载 / 音频 / 转录 / 笔记 / 导图 / 清理）、当前百分比与预计剩余耗时，且这些数据 MUST 通过近实时刷新（v1 短轮询）更新而无需手动刷新

#### Scenario: 进行中任务卡可进入任务详情

- **WHEN** 用户点击某张进行中任务卡的「查看详情」
- **THEN** 应用 MUST 导航到该任务的「任务详情」页，且详情页加载的任务 ID MUST 与所点任务卡一致

#### Scenario: 最近完成表格提供产物入口

- **WHEN** 主控台最近完成表格渲染完成
- **THEN** 每行已完成任务 MUST 提供进入「笔记」「思维导图」与下载 SRT 的入口，点击「笔记」MUST 导航到该任务的笔记页

### Requirement: 任务详情六步流水线节点可视化

任务详情页 MUST 以 DAG 串行形式可视化六步流水线(下载 → 提取音频 → 转录 → 整理笔记 → 思维导图 → 清理),每个节点 MUST 实时呈现其状态(完成 / 运行中 / 等待 / 失败 / 跳过)、产物标签(文件名与大小或「待生成」)与本节点耗时,并 MUST 提供跟随整体进度的进度环与进度条。

#### Scenario: 六节点按 DAG 串行展示且状态实时变化

- **WHEN** 用户打开一个处于「转录中」的任务详情页
- **THEN** 流水线 MUST 按顺序渲染六个节点,其中「下载」「提取音频」 MUST 标记为完成、「转录」 MUST 标记为运行中、其后三节点 MUST 标记为等待;当后端推进到下一节点时,前端 MUST 通过 SSE 更新对应节点状态而无需刷新

#### Scenario: 每个节点展示产物标签与耗时

- **WHEN** 某节点(例如「下载」)完成
- **THEN** 该节点 MUST 展示其产物的标签(如 `video.mp4 · 184.2 MB`)与本节点耗时(如 `18s`);尚未开始的节点 MUST 展示「待生成」与耗时占位「—」

#### Scenario: 进度环与进度条跟随整体百分比

- **WHEN** 任务整体百分比由 SSE 更新为新值
- **THEN** 侧列的环形进度指示器与条形进度条 MUST 同步更新到该百分比,环中心 MUST 显示该百分比数字

#### Scenario: 跳过节点按来源类型正确显示

- **WHEN** 任务来源为「本地音频」(上传音频文件,跳过下载与音频提取)
- **THEN** 「下载」与「提取音频」节点 MUST 被标记为跳过(与「等待」状态视觉可区分),流水线 MUST 从「转录」节点开始推进

### Requirement: 任务详情实时日志终端

任务详情页 MUST 提供一个连接后端 SSE 的实时日志终端,在任务运行期间 MUST 增量追加后端推送的日志行,每行 MUST 带时间戳并按日志级别(info / ok / dim / 错误)着色区分;日志终端 MUST 在任务到达终态后停止增长但保留已接收的历史日志。

#### Scenario: 打开任务详情即建立 SSE 并增量追加日志

- **WHEN** 用户打开一个运行中任务的详情页
- **THEN** 前端 MUST 通过同源 `/api/v1/tasks/{task_id}/stream` 与后端建立 SSE 连接,后端每推送一条日志,终端 MUST 增量追加一行,且 MUST NOT 重复追加已接收的行

#### Scenario: 日志按级别着色并带时间戳

- **WHEN** 终端渲染一条日志行
- **THEN** 该行 MUST 包含时间戳,且 info / ok / 错误等不同级别 MUST 通过不同颜色或前缀可区分

#### Scenario: 终态后日志停止增长但保留历史

- **WHEN** 任务进入「完成」或「失败」终态
- **THEN** 日志终端 MUST 停止追加新行,已显示的历史日志 MUST 保持可见不被清空,SSE 连接 MUST 被正确关闭而不得泄漏

### Requirement: 任务详情产物 Tab 与重跑取消

任务详情页 MUST 提供产物 Tab 切换(至少包含转录稿、笔记预览、元数据三个面板),并 MUST 在顶部操作区根据任务状态提供「重跑」与「取消任务」操作:运行中任务 MUST 可取消,失败任务 MUST 可发起重跑,已完成任务 MUST 可重跑,未达可操作状态时对应按钮 MUST 被禁用或隐藏。

#### Scenario: 产物 Tab 切换展示对应内容

- **WHEN** 用户在任务详情的产物区点击「转录稿」「笔记预览」「元数据」三个 Tab 之一
- **THEN** 面板 MUST 切换到对应内容(转录稿展示带时间戳的字幕行、笔记预览展示渲染后的 Markdown、元数据展示任务 ID / 来源 / 时长 / ASR / LLM 等键值),且同一时刻 MUST 只有当前 Tab 处于激活态

#### Scenario: 运行中任务可取消

- **WHEN** 任务处于运行中状态且用户点击「取消任务」
- **THEN** 前端 MUST 调用后端取消接口,任务状态 MUST 转为已取消 / 失败,流水线节点 MUST 停止推进

#### Scenario: 失败任务可发起重跑

- **WHEN** 任务处于失败状态且用户点击「重跑」
- **THEN** 前端 MUST 调用后端重跑接口发起一次新的执行,任务 MUST 重新进入运行态,且重跑 MUST 在干净工作区进行(不得残留上次失败半成品,此行为由后端保障,前端仅负责触发与状态反馈)

#### Scenario: 未达可操作状态时按钮不可用

- **WHEN** 任务处于排队中尚未开始,或已被取消
- **THEN** 「取消任务」与「重跑」中不适用当前状态的那个按钮 MUST 被禁用或隐藏,点击无效

### Requirement: 笔记页 Markdown 渲染与导出

笔记页 MUST 正确渲染后端生成的 Markdown 笔记(含标题、段落、代码块、引用、有序 / 无序列表、时间戳标记),MUST 提供「复制 Markdown」「导出 .md」操作产出与渲染内容一致的源文本,MUST 提供进入思维导图页的入口,并 MUST 提供章节大纲与可选的 PDF 讲义双栏对照。

#### Scenario: Markdown 正文正确渲染

- **WHEN** 用户打开一篇已生成笔记
- **THEN** 页面 MUST 将 Markdown 源文渲染为带样式的正文,标题 / 代码块 / 引用 / 列表 / 行内时间戳标记 MUST 各自正确呈现,且渲染 MUST 与源文结构一致

#### Scenario: 复制与导出产出源文

- **WHEN** 用户点击「复制 Markdown」或「导出 .md」
- **THEN** 复制操作 MUST 将该笔记的 Markdown 源文写入剪贴板,导出操作 MUST 下载一个 `.md` 文件,二者的内容 MUST 与后端存储的笔记源文一致,MUST NOT 包含渲染产生的 HTML 标签

#### Scenario: 章节大纲可定位

- **WHEN** 笔记页存在章节大纲且用户点击其中某一条
- **THEN** 正文 MUST 滚动定位到对应章节,且当前定位章节 MUST 在大纲中有可区分的高亮

#### Scenario: 思维导图入口跳转

- **WHEN** 用户在笔记页点击「思维导图」入口
- **THEN** 应用 MUST 导航到该任务的思维导图页,且导图页加载的任务 ID MUST 与当前笔记所属任务一致

#### Scenario: PDF 讲义对照开关切换双栏

- **WHEN** 用户在笔记页打开「PDF 讲义对照」开关
- **THEN** 页面 MUST 切换为左栏视频笔记、右栏讲义 PDF 的双栏对照布局;关闭开关时 MUST 恢复单栏笔记视图

### Requirement: 思维导图页导出

思维导图页 MUST 在页面上以只读方式可视化预览当前任务的思维导图（基于已生成笔记的标题层级渲染为节点 + 父子连线），MUST 支持将导图导出为三种格式：`.xmind`、`.png` 图片、`.md` 大纲；MUST 提供缩放（放大 / 缩小）、适应、居中等视图控制以及与导图同构的文本大纲面板；MUST 支持点击节点对其子树折叠 / 展开（仅作查看便利，不构成编辑）。v1 MUST NOT 要求思维导图页支持节点增删改、连线编辑等交互式编辑能力（仅查看与导出）。

#### Scenario: 导出 xmind 产出 .xmind 文件

- **WHEN** 用户点击「导出 xmind」
- **THEN** 前端 MUST 触发后端生成并下载一个 `.xmind` 文件，该文件 MUST 能被 XMind 类客户端正常打开

#### Scenario: 导出 PNG 产出图片

- **WHEN** 用户点击「导出 PNG」
- **THEN** 前端 MUST 触发后端将导图渲染为图片并下载一个 `.png` 文件，图片内容 MUST 与页面所示导图一致

#### Scenario: 导出大纲 .md 产出 markdown 大纲

- **WHEN** 用户点击「导出大纲 .md」
- **THEN** 前端 MUST 下载一个以 Markdown 缩进表达导图层级的 `.md` 大纲文件，其层级 MUST 与页面文本大纲一致

#### Scenario: 缩放与视图控制

- **WHEN** 用户点击放大 / 缩小 / 适应 / 居中按钮
- **THEN** 导图画布 MUST 按操作缩放或复位视图，缩放百分比指示 MUST 同步更新

#### Scenario: 只读可视化预览

- **WHEN** 用户打开一个已生成笔记任务的思维导图页
- **THEN** 页面 MUST 将该笔记的标题层级渲染为可读的思维导图预览（节点带文字、父子节点间存在连线），且页面 MUST NOT 提供节点增删改或连线编辑的入口

#### Scenario: 节点折叠与展开

- **WHEN** 用户点击导图预览中某个含子节点的节点
- **THEN** 该节点的子树 MUST 折叠隐藏，再次点击 MUST 展开；折叠 / 展开 MUST NOT 改变导出的导图内容，页面 MUST NOT 因此出现任何编辑能力

#### Scenario: 文本大纲面板与导图同构

- **WHEN** 思维导图页渲染导图预览
- **THEN** 页面 MUST 同时（并排或可切换）展示与导图同构的缩进文本大纲面板，其层级 MUST 与导图预览及 `.md` 大纲导出三者一致

### Requirement: 历史页筛选分页与批量操作

历史页 MUST 以表格列出全部任务,并 MUST 提供三类筛选:状态(全部 / 进行中 / 已完成 / 失败)、来源(全部来源 / 链接 / 上传 / PDF 对照)、关键词(按标题、链接、任务 ID 搜索);MUST 支持分页浏览;MUST 支持行多选后的批量导出,以及对失败任务行的重跑。

#### Scenario: 状态筛选

- **WHEN** 用户点击状态筛选中的「失败」
- **THEN** 表格 MUST 仅显示状态为失败的任务,其他任务 MUST NOT 出现,且各状态筛选 chip 上 MUST 展示对应任务计数

#### Scenario: 来源筛选

- **WHEN** 用户选择来源筛选的「上传」
- **THEN** 表格 MUST 仅显示来源为本地上传的任务(本地视频与本地音频),在线链接与 PDF 对照任务 MUST NOT 出现

#### Scenario: 关键词搜索

- **WHEN** 用户在搜索框输入一个任务 ID 片段或标题关键词
- **THEN** 表格 MUST 实时过滤出标题、链接或任务 ID 中包含该关键词的任务,且筛选 MUST 与状态 / 来源筛选可叠加生效

#### Scenario: 分页浏览

- **WHEN** 任务总数超过单页容量且用户点击下一页
- **THEN** 表格 MUST 切换到对应页的任务,分页器 MUST 展示「显示 X–Y / 共 Z 条」区间与可用的翻页按钮,首页的「上一页」MUST 被禁用

#### Scenario: 多选后批量导出

- **WHEN** 用户勾选多行任务后点击「批量导出」
- **THEN** 前端 MUST 将所选任务的笔记(及可选的其他产物)打包导出,导出范围 MUST 与所选行一致,未勾选的任务 MUST NOT 被包含

#### Scenario: 失败任务行可重跑

- **WHEN** 历史表格中某行任务状态为失败
- **THEN** 该行操作列 MUST 提供「重跑」按钮,点击后 MUST 调用后端重跑接口并使该任务重新进入运行态

### Requirement: 设置页 ASR 与 LLM 引擎配置

设置中心 MUST 采用「通用 / LLM 服务 / 笔记生成 / 存储与清理 / 高级设置 / 关于」六个页签。设置中心 MUST NOT 再提供第二套完整 ASR 表单，只 SHALL 展示当前 ASR 摘要与进入独立 ASR 页的入口。LLM 页签 MUST 展示八家内置 provider 和一个自定义 OpenAI-compatible 槽位，允许分别编辑模型、Base URL 和所需凭证，并有且仅有一个默认 provider。已配置凭证输入框 MUST 默认显示黑点和配置状态，右侧 MUST 提供可访问的眼睛按钮按需切换明文。

#### Scenario: 六个设置页签切换

- **WHEN** 用户打开设置中心并依次点击六个页签
- **THEN** 页面 MUST 只展示当前页签内容，切换 MUST NOT 丢失尚未保存的同页编辑状态，窄屏下页签 MUST 可横向滚动或换行且不得溢出

#### Scenario: 设置页只显示 ASR 摘要

- **WHEN** 用户在设置中心查看通用或相关摘要区域
- **THEN** 页面 SHALL 显示当前默认 ASR 和策略，并提供「前往 ASR 设置」，MUST NOT 出现可与独立 ASR 页产生冲突的第二套完整编辑表单

#### Scenario: 九种 LLM 槽位各可配置

- **WHEN** 用户进入 LLM 服务页签
- **THEN** 页面 MUST 列出 DeepSeek、Qwen、GLM、Kimi、百度千帆、豆包、MiniMax、Ollama 和自定义槽位，并展示默认/已配置/未配置/本地等状态

#### Scenario: 模型有建议值且允许自由填写

- **WHEN** 用户选择任一内置 provider
- **THEN** 模型输入框 MUST 初始显示该 provider 的建议模型 ID，并允许用户直接编辑成其他非空 ID

#### Scenario: 已配置密钥默认显示黑点

- **WHEN** 某 provider 的 API Key 已保存并重新加载页面
- **THEN** 输入框 MUST 显示黑点而非空白，旁边 MUST 显示「已配置」和安全尾号，使用户可区分未配置状态

#### Scenario: 眼睛按钮查看与隐藏明文

- **WHEN** 用户点击密钥框右侧眼睛按钮
- **THEN** 页面 MUST 按需读取并显示明文；再次点击、切换 provider/页签或超时后 MUST 恢复黑点并清除明文

#### Scenario: LLM 默认提供商为 DeepSeek

- **WHEN** 首次启动且没有任何 LLM 配置
- **THEN** 默认 provider MUST 为 DeepSeek、模型 MUST 为 `deepseek-v4-flash`，主控台新建任务的 LLM 默认项 MUST 与之一致

#### Scenario: Ollama 与自定义地址可配置

- **WHEN** 用户选择 Ollama 或自定义槽位
- **THEN** 页面 MUST 允许填写容器可达的 Base URL；Ollama SHALL 提示 API Key 非必需，自定义槽位 MUST 要求非空名称、模型和 URL

### Requirement: 设置页处理选项

设置中心 MUST 在对应页签提供界面语言、背景、输出语言、四档笔记详细程度、图片提取与质量、PDF 模式、并发任务数（1~3）、分块大小、Temperature、最大重试次数和五类保留策略。截图嵌入 SHALL 继续作为新建任务的逐任务选项，但设置页可提供新任务默认值。PDF 只展示当前稳定的 `pypdf`，MUST NOT 展示未实现的 MinerU 选择。

#### Scenario: 笔记详细程度四档可选

- **WHEN** 用户在笔记生成页签选择「简洁 / 适中 / 详细 / 超详细」之一并保存
- **THEN** `note.detail_level` MUST 保存为对应合法值，页面 MUST 解释该档位对覆盖率和 token/耗时的影响，后续新建任务 MUST 使用该默认档位

#### Scenario: 截图嵌入逐任务选择

- **WHEN** 用户在主控台创建任务
- **THEN** 截图开关 MUST 以设置默认值预填且仍可为本次任务覆盖，本次选择 SHALL 只影响本任务

#### Scenario: 并发任务数限定 1~3 且越界被拒

- **WHEN** 用户尝试将并发任务数设为 0 或 4(或范围外的任意值)并保存
- **THEN** 前端 MUST 校验失败并阻止保存；合法值 MUST 保存成功

#### Scenario: 高级数值显示范围与说明

- **WHEN** 用户打开高级设置
- **THEN** chunk size、Temperature 和最大重试次数 MUST 以带最小值/最大值/用途说明的数字字段展示，非法值 MUST 在提交前提示

#### Scenario: 保存反馈不使用阻塞弹窗

- **WHEN** 用户保存任一页签
- **THEN** 页面 MUST 以页内状态或 toast 展示保存中、成功或错误，MUST NOT 使用浏览器原生 `alert`

### Requirement: 设置页产物保留策略配置

设置页 MUST 为五类产物(视频 / 音频 / SRT / 笔记 / 截图)各自提供独立的保留策略选择,每一类的取值 MUST 限定为「永久」「7 天」「30 天」三者之一;修改任意一类的策略 MUST NOT 影响其他四类。保存后配置 MUST 对后续清理逻辑生效。

#### Scenario: 五类产物各自独立选择保留策略

- **WHEN** 用户将视频设为「7 天」、笔记设为「永久」、截图设为「30 天」并保存
- **THEN** 三类 MUST 分别保存为各自被设置的值,音频与 SRT MUST 保持原值不变,前端 MUST 反馈保存成功

#### Scenario: 修改一类不影响其他类

- **WHEN** 用户仅修改「音频」的保留策略并保存
- **THEN** 其余四类产物的保留策略 MUST 保持不变,MUST NOT 因音频的修改而被改动

### Requirement: 国际化与明暗主题

前端 MUST 支持中文与英文两种界面语言（经 `vue-i18n` 实现，UI 文案抽取为 locale key，`zh` 与 `en` 两套），并 MUST 支持明色与暗色两种主题；语言与主题的切换 MUST 全站生效（覆盖所有页面的 UI 文案与控件可读文案），且用户选择 MUST 被持久化（语言存 `localStorage`），刷新或重启容器后 MUST 保留。笔记正文与思维导图内容（LLM 产物原文）MUST NOT 被 i18n 改写，只翻译 UI 框架文案。

#### Scenario: 中英文切换全站生效

- **WHEN** 用户在设置页将界面语言从中文切换为英文（或反之）
- **THEN** 当前页面及导航至其他任一页面时，所有用户可见的 UI 文案 MUST 切换为对应语言（经 `$t` 渲染），MUST NOT 出现混用两种语言的残留文案；笔记正文与导图节点内容 MUST 保持产物原文不受影响

#### Scenario: 明暗主题切换并持久化

- **WHEN** 用户点击主题切换按钮将主题从明色切到暗色（或反之）后刷新页面
- **THEN** 全站 MUST 立即应用新主题，刷新后 MUST 保留用户选择的主题而非回退到默认

#### Scenario: 首次访问提供合理默认

- **WHEN** 用户首次在无任何偏好存档的情况下访问应用
- **THEN** 前端 MUST 提供一个确定的默认语言（中文）与默认主题（或跟随系统明暗偏好），MUST NOT 出现未渲染文案（显示裸 key）或无主题的中间态

#### Scenario: 语言选择持久化到本地

- **WHEN** 用户选择英文后关闭并重新打开浏览器
- **THEN** 应用 MUST 读取 `localStorage` 并以英文呈现 UI，MUST NOT 回退到中文默认

### Requirement: 液态玻璃设计系统(分层玻璃)
系统 SHALL 提供分层液态玻璃视觉:浮起层(侧栏 / 顶栏 / 弹层 / 浮卡)使用 `backdrop-filter: blur()+saturate()` 半透明玻璃,背后背景透出;主内容区卡片使用半透明纯色(非玻璃)以保证可读性。

#### Scenario: 浮起层呈现玻璃
- **WHEN** 用户查看主界面
- **THEN** 侧栏与顶栏呈现 `backdrop-filter` 模糊+饱和的半透明玻璃,mesh 背景透出,带 1px 高光内边

#### Scenario: 内容区保证可读
- **WHEN** 用户查看笔记 / 列表等内容区
- **THEN** 内容卡片为半透明纯色(非 `backdrop-filter` 玻璃),文字对比度满足可读性

#### Scenario: 双主题平滑切换
- **WHEN** 用户切换明 / 暗主题
- **THEN** 玻璃与内容区颜色平滑过渡(过渡 ≤250ms),文字保持可读对比度,选择持久化

### Requirement: 物理动效系统(emil 哲学·克制)
系统 SHALL 提供克制的 iOS spring 动效:可点元素 press `scale(.97)`;弹层从触发点 origin 缩放进入(modal 例外居中);页面切换淡入 + 上移 8px;列表 stagger(40ms);退出比进入快;统一 spring 曲线 `cubic-bezier(0.32,0.72,0,1)`。

#### Scenario: 按压即时反馈
- **WHEN** 用户按下按钮 / 可点元素
- **THEN** 元素 `scale(.97)` 即时回应,松开后 spring 回弹

#### Scenario: 弹层 origin-aware
- **WHEN** 用户从某触发点打开弹层 / 浮卡
- **THEN** 弹层从触发点位置(origin)缩放进入,而非居中(modal 类例外居中)

#### Scenario: reduced-motion 降级
- **WHEN** 用户系统开启「减少动效」
- **THEN** 移除位移 / 缩放类动效,仅保留淡入,保证不引发不适

### Requirement: 流水线节点招牌动效
任务详情的六步流水线节点 SHALL 用动效直观传达状态:节点完成时 spring 弹动 + 成功色光晕;运行中 Apple 蓝呼吸光;失败时抖动 + 警示色;完成段连接线 clip-path 擦除式流光填充。

#### Scenario: 节点完成
- **WHEN** 某节点状态变为 completed
- **THEN** 节点 spring 缩放(1→1.15→1)+ 成功色光晕脉冲一次

#### Scenario: 节点运行中
- **WHEN** 某节点 running
- **THEN** 节点 Apple 蓝呼吸光脉冲(循环)

#### Scenario: 节点失败
- **WHEN** 某节点 failed
- **THEN** 节点横向抖动 + 红色警示色

#### Scenario: 连接线流光
- **WHEN** 上游节点完成
- **THEN** 该段连接线以 clip-path 擦除式流光填充至下游节点

### Requirement: 动态背景与背景可配
系统 SHALL 默认提供动态 mesh 渐变背景(多色径向色斑缓慢漂移),用户可在设置页切换为静态壁纸或纯色;背景动效 SHALL 尊重 `prefers-reduced-motion`(降级为静态首帧)。

#### Scenario: 默认动态 mesh
- **WHEN** 用户首次打开(默认配置)
- **THEN** 背景为多色径向色斑缓慢漂移(20–30s 周期)的 mesh 渐变

#### Scenario: 用户切换背景
- **WHEN** 用户在设置页选择静态壁纸 / 纯色
- **THEN** 背景立即切换并持久化,刷新 / 重启后保留

#### Scenario: 背景降级
- **WHEN** 系统开启减少动效
- **THEN** mesh 停止漂移,呈现静态首帧

### Requirement: 笔记舒适阅读排版
笔记页 SHALL 采用舒适阅读排版:正文限宽 720px 居中;标题用衬线字体;正文行距 1.8;正文字号 16px;代码块 / 引用用玻璃浮卡承载。

#### Scenario: 阅读布局
- **WHEN** 用户打开笔记页
- **THEN** 正文限宽 720px 居中,标题衬线,行距 1.8,字号 16px,长笔记阅读不累

### Requirement: 设计系统沉淀(DESIGN.md)
项目 SHALL 沉淀 `DESIGN.md` 全套设计文档(设计 token 表 + 玻璃组件库 API + 动效规范 + 页面模板 + do/don't + 暗主题对照),供后续页面开发复用,避免风格漂移。

#### Scenario: DESIGN.md 完整产出
- **WHEN** 本次重构完成
- **THEN** 项目根(或 docs/)存在 `DESIGN.md`,含六节(token / 组件库 / 动效规范 / 页面模板 / do-don't / 暗主题),后续新页面可据此复用

### Requirement: ASR 管理页

系统 MUST 保留一个经侧栏到达的独立 ASR 管理页，并采用「引擎 / Whisper 本地 / 外部 ASR / 转录策略」四个内部页签。页面 MUST 集中承载三种引擎的说明、默认选择、配置和诊断。实验性在线 ASR 的用户可见名称 MUST 为「bcut」，不得暗示官方、稳定或保证免费，也不得暴露内部兼容实现名。

#### Scenario: 四个 ASR 页签职责清晰

- **WHEN** 用户依次切换四个 ASR 页签
- **THEN** 引擎页 MUST 展示三引擎卡片与总览，Whisper 页 MUST 展示本地模型参数，外部页 MUST 展示 endpoint/凭证，策略页 MUST 展示降级/VAD/并发参数

#### Scenario: 三引擎说明可见

- **WHEN** 用户打开 ASR 的引擎页签
- **THEN** 页面 MUST 展示 bcut（在线、实验性、无需本地 GPU）、Whisper 本地（离线、CPU）与外部 ASR（自建 HTTP）三张卡片，每张 MUST 含适用场景、当前状态和测试入口

#### Scenario: 默认引擎与策略持久化

- **WHEN** 用户选择默认引擎为 bcut、策略为在线优先并保存
- **THEN** `asr.engine` / `asr.strategy` MUST 持久化，刷新或重启后保留，主控台默认引擎 MUST 同步

#### Scenario: Whisper 参数可配置

- **WHEN** 用户填写模型路径、可选 binary 和识别语言并保存
- **THEN** 配置 MUST 在 Whisper 页重新加载时完整显示，状态区 MUST 基于后端检查展示模型和 binary 是否就绪

#### Scenario: 外部 endpoint 和密钥可配置

- **WHEN** 用户填写外部 ASR endpoint、API Key 与超时并保存
- **THEN** endpoint 与超时 MUST 写入非敏感设置，API Key MUST 进入加密凭证存储；重新加载时密钥框 MUST 显示已配置黑点

#### Scenario: 连通性测试反馈结果

- **WHEN** 用户对某个引擎点击「测试连接」
- **THEN** 前端 MUST 调用后端测试接口并反馈成功耗时或失败原因，MUST NOT 在未测试时声称连接可用

#### Scenario: 页面响应式可用

- **WHEN** 页面宽度缩小到手机尺寸
- **THEN** 页签、引擎卡片、表单与操作按钮 MUST 重排为单列或可滚动布局，MUST NOT 出现水平页面溢出或被遮挡的保存按钮

### Requirement: 笔记与思维导图全量浏览页

系统 MUST 提供两个全量浏览页（经侧栏「笔记」「思维导图」进入）：笔记浏览页 `/notes` 与导图浏览页 `/mindmaps`，各自采用左 / 中 / 右三栏布局。左栏 MUST 列出全部已完成任务（按时间倒序），MUST 提供按标题 / 链接 / 来源的搜索，MUST 默认选中最新一篇，且每项 MUST 按「列表项统一命名」格式展示。中栏 MUST 渲染当前选中任务的笔记正文（Markdown 渲染，限宽）或思维导图（只读预览，可缩放 / 折叠）。右栏 MUST 提供「大纲」与「操作」两个 Tab：大纲 Tab 展示与中栏同构的章节大纲（笔记）或文本大纲（导图），点击大纲项 MUST 定位中栏；操作 Tab MUST 提供导出、复制（笔记）、跳转另一页与任务元信息。列表项切换 MUST 让中栏与右栏联动更新。

#### Scenario: 左栏列出全部已完成任务并可搜索

- **WHEN** 用户从侧栏进入笔记浏览页（或导图浏览页）
- **THEN** 左栏 MUST 列出全部已完成任务，按时间倒序，默认选中第一篇（最新）；在搜索框输入关键词后，列表 MUST 实时过滤出标题 / 链接 / 来源匹配的任务

#### Scenario: 中栏渲染选中项内容

- **WHEN** 用户在左栏点选某任务
- **THEN** 中栏 MUST 加载并渲染该任务的笔记正文（笔记页）或思维导图预览（导图页）；切换选中时中栏 MUST 联动更新为新选中项的内容

#### Scenario: 右栏大纲定位与操作

- **WHEN** 用户在右栏「大纲」Tab 点击某章节（或导图大纲节点）
- **THEN** 中栏 MUST 滚动定位到对应章节；切到「操作」Tab 时 MUST 能触发导出 / 复制（笔记）/ 跳转另一页，并展示任务元信息

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

### Requirement: 任务详情页展示 LLM 消耗

任务详情页 MUST 在任务产生过 LLM 用量数据时展示「LLM 消耗」区块：按阶段（证据理解、全局蓝图、章节深写、章节审校、思维导图、其他）以表格展示调用次数、输入 tokens、缓存命中 tokens、缓存未命中 tokens、输出 tokens 与输入命中率，并含总计行。任务无用量数据时 MUST NOT 渲染该区块。数字 MUST 使用等宽对齐样式，文案 MUST 提供中英文。

#### Scenario: 有用量的任务展示分阶段表格

- **WHEN** 用户打开一个 `llm_usage.total.calls > 0` 的任务详情
- **THEN** 页面 MUST 显示「LLM 消耗」区块，每个有调用的阶段各占一行，总计行与各阶段行数值一致勾稽

#### Scenario: 无用量任务不显示区块

- **WHEN** 用户打开一个无 `llm_usage` 数据的历史任务详情
- **THEN** 页面 MUST NOT 显示「LLM 消耗」区块，其余内容不受影响

