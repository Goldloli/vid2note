# vid2note v1 —— 技术设计

> 变更:`build-vid2note-v1` · 形态:Docker 部署的本地 Web 应用(`localhost:8765`),个人本地自用,无登录。
> 基底:fork 作者自有的 `ai_srt2md`(FastAPI:8765 + Vue3 + SQLite + 8 家 LLM 适配 + PDF 对照 + 思维导图 + prompt 库)。
> 本文与同目录 `proposal.md`、`specs/*/spec.md` 配套;spec 用 Scenario 约束「做什么」,本文负责「怎么做、为什么这么做」。

---

## Context

**场景与动机。** 看视频做笔记是高频却割裂的体力活:手动下载、提取音频、转字幕、整理结构化笔记,工具链冗长。vid2note 把它压缩成「粘链接 → 拿 Markdown 笔记 + 思维导图」的一条本地流水线。

**现状:fork ai_srt2md。** 作者已有的 `ai_srt2md`(/Volumes/worknie/Desktop/ai_code/ai_srt2md)是一条「字幕 → 笔记」链路,工程上已成熟,可直接作为 v1 基底:

- 后端 FastAPI(:8765),`backend/src/main.py` + `api/` 路由;SQLite 持久化(`db/task_repository.py`);异步任务队列 `core/task_queue.py`(`max_concurrent` 可配);后台 worker `core/worker.py`。
- LLM 适配层 `llm/`(8 家:deepseek/qwen/glm/moonshot/minimax/doubao/baidu/mock,统一走 OpenAI 兼容协议,`factory.py` 工厂),prompt 库 `prompts/`(restructure / generate_directly / generate_with_pdf_reference / classify / mindmap / mindmap_outline / pdf_structure_analysis)。
- 字幕→笔记核心 `core/simple_processor.py`(PDF 结构优先,再对齐字幕)、语义对齐 `core/aligner.py`、内容过滤 `core/filter.py`、Markdown 生成 `core/generator.py`。
- 解析器 `parsers/`(srt/pdf/txt;PDF 用 PyMuPDF + pypdf)、思维导图导出(xmind/png/md)、安全:`utils/security.py` + `core/security_constants.py`(提示词注入防护)、`utils/srt_validator.py`(SRT 校验)。
- 前端 Vue3(`frontend/src/`,router/stores/api 对接模式齐备)。
- 现状部署为**双容器**:`backend`(FastAPI:8765)+ `frontend`(Nginx:80),见 `docker-compose.yml`。

**约束。**

- **本地 / Docker**:macOS arm64 优先,单条 `docker compose up` 起服务,浏览器访问 `localhost:8765`。
- **无 GPU**:ASR 与 MinerU 一律走 CPU;仅留「外部服务 endpoint」扩展位给未来的 GPU/MLX。
- **个人自用,无登录**:不做鉴权/多用户/远程访问;但 bilibili 高画质需用户在设置页粘贴 cookie。
- **字幕一律走 ASR**:v1 不抓官方字幕(CC),不分支。
- **默认 LLM = DeepSeek `deepseek-v4-flash`**。

**六步流水线。** 下载(yt-dlp)→ 提取音频(ffmpeg)→ ASR 转录 → LLM 整理笔记(+可选截图嵌入)→ 思维导图 → 清理。来源为本地音视频时相应跳过前 1~2 步。

---

## Goals / Non-Goals

### Goals

1. **一条命令可用**:`docker compose up` 后 `localhost:8765` 即完整前后端同源服务。
2. **粘链接出笔记**:YouTube / Bilibili / 直链 / 本地音视频四类输入,自动跑通六步,产出 Markdown 笔记 + 思维导图(xmind/png/md)。
3. **ASR 优先在线、本地兜底**:实验性 bcut 默认在线,whisper.cpp(CPU + int8)兜底,失败可显式降级,全程对调用方透明。
4. **长音频可扛**:VAD 按静音切分并行转录,时间戳偏移拼回一份连续单调的 SRT。
5. **最大化复用基底**:LLM 适配、prompt 库、SRT→笔记、SQLite、安全防护、思维导图导出原样复用;改造聚焦在「输入端 + 编排层 + 新集成」。
6. **可观测 / 可重跑**:6 步 DAG 可视化、SSE 实时进度、节点级失败重跑(不必从头重下载)。
7. **磁盘可控**:五类产物各自独立保留策略(永久 / 7d / 30d),自动清理。

### Non-Goals(v1 不做,留待以后)

- Electron 桌面客户端、扫码登录、远程/多用户/账号鉴权。
- GPU / MLX 加速;MinerU 的 vLLM / 高精度 GPU 引擎。
- 交互式思维导图页(v1 仅导出 xmind/png/md 大纲)。
- 平台官方字幕(CC)抓取与切换分支。
- 截图嵌入的高精度优化(v1 接受纯文本 LLM 的猜测精度)。

---

## Decisions

### D1. 部署形态:单容器(FastAPI 同源托管 API + 前端静态资源)

**决策。** 放弃基底的双容器(backend:8765 + Nginx:80),收敛为**单容器**:FastAPI 进程在 8765 既挂 API 路由,又 `app.mount("/", StaticFiles(...))` 托管前端构建产物。一条 `docker compose up`、一个端口、同源访问。

**理由(为何选 X 不选 Y)。** spec 的 `docker-deployment` 明确要求「单条命令拉起前后端」「`localhost:8765` 同源可达」「不得因 CORS 或端口差异失败」。单容器天然同源,消除了 CORS 中间件、Nginx 反代、双服务健康依赖这一整层复杂度;个人本地自用下,前端静态托管的开销可忽略,把 Nginx 留在链路里纯粹是遗留形态。基底的 `main.py` 已用 `CORSMiddleware(allow_origins=["*"])`,单容器后该中间件可直接移除,减少攻击面。

**Alternatives。**
- *双容器(沿用基底 backend + Nginx):* 部署链更长、要管两个镜像/健康检查/网络别名,且 80 端口在 Mac 上常被占用,违反「localhost:8765」与「同源」要求。否决。
- *Caddy / Traefik 反代 + 后端:* 多一个进程只为反代,过度工程。否决。
- *Vite 开发服务器直接暴露:* 仅供开发,不适合 `docker compose up` 产物形态。否决。

### D2. ASR 引擎:抽象 `AsrEngine` 接口 + 三实现 + 两种选择策略

**决策。** 新建 `speech_to_text/engine.py` 定义统一接口(`transcribe(audio_path) -> List[Cue]`,Cue = {start, end, text}),三实现:`BcutEngine`(实验性在线 bcut,默认首选)、`WhisperCppEngine`(本地 CPU + int8)、`ExternalAsrEngine`(HTTP endpoint,扩展位)。引擎来源与策略均来自配置项;两种策略:「在线优先,失败转本地」(默认)与「指定单一引擎」。每次降级写一条结构化日志(原因 / 原引擎 / 目标引擎 / 时间戳)。

**理由。** 约束是「无 GPU」但又要「质量好 + 离线兜底」。实验性在线 bcut 走纯 HTTP、无需本地 GPU,做默认;whisper.cpp 用 int8 量化在 arm64 CPU 上可用,做兜底保证「断网也能出字幕」;external endpoint 留给未来接自建 GPU ASR,接口先占位。「在线优先」在外部能力可用时优先在线处理,失败则降级而不阻塞用户;「指定单一引擎」给「我就要纯本地/我就要在线」的强需求。

**Alternatives。**
- *仅 whisper.cpp:* 纯本地、零依赖,但 CPU 长音频慢、中文质量不如剪映,默认体验差。作为兜底保留,不作唯一。
- *仅 bcut:* 依赖网络与外部服务可用性,断网/限流/协议变化即全停,无兜底。否决。
- *whisper 大模型(GPU):* 违反「无 GPU」约束。否决。
- *`faster-whisper` Python 绑定代替 whisper.cpp:* 见 Open Questions,需评估依赖体积与 arm64 兼容。

### D3. 长音频:VAD 按静音切分 + 并行转录 + 时间戳偏移拼回

**决策。** 输入音频超过单次转写阈值(初定 5 分钟)时,先用 VAD 检测静音边界切分为多段,对各段**并行**调用所选 `AsrEngine`(并发受 D8 任务内并发上限约束),每段字幕的 `start/end` 叠加该段在原音频中的起始偏移,拼回一份时间戳严格单调递增、覆盖完整时长的 SRT。分段与拼合在 `speech_to-text` 内部完成,调用方(笔记生成步骤)只看到一份完整 SRT。

**理由。** 单次喂超长音频会触发引擎长度上限或质量退化;**固定时长切片**会从词语中间切断,拼回后语义破碎;**VAD 按静音切**天然落在停顿处,不破坏词边界。并行转录把长音频的墙钟时间压到「最长那一段」量级;偏移叠加是确定性算术,可单测(段从 300s 开始、段内 10s → 拼回 310s)。拼合处做一次单调化校验(与基底的 `srt_validator.py` 同源),保证跨段不重叠、不空洞。

**Alternatives。**
- *固定窗口切片(如每 5 分钟硬切):* 实现最简,但会截断词句,字幕质量受损。否决。
- *不分片,串行整段:* 触发长度上限 / 质量降,且无并行加速。否决。
- *流式 ASR(streaming):* 引擎支持度不一、实现复杂、时间戳对齐难,v1 不值。否决。

### D4. 截图嵌入:`[IMG:ts]` LLM 标记 + 后端 ffmpeg 截帧替换(默认关)

**决策。** 截图嵌入做成**任务级开关,默认关**。开启时:笔记生成步骤把字幕连同时间戳以纯文本注入 prompt(`generate_directly` / `generate_with_pdf_reference` 的 v1 扩展分支),指示 LLM 在「此处需要一张图 / 此处是重点画面」处输出标记 `[IMG:HH:MM:SS]`;笔记后处理用正则扫标记,对每个合法时间戳调 `ffmpeg -ss <ts> -i <video> -frames:v 1` 截帧,落盘到 `screenshots/`,并把标记替换为 Markdown 图片引用;非法 / 越界时间戳静默跳过并记日志。

**理由。** 约束是「无 GPU、省 token」。**多模态 LLM 直接看视频帧**会把 token 成本与延迟拉到不可接受,且多数适配厂商多模态能力参差;让**纯文本 LLM 决策「何时需图」**是廉价的语义判断,真正的「截哪一帧」交给 ffmpeg 按精确时间戳完成,确定性、零幻觉成本。v1 接受「LLM 标记位置可能不够准」(Non-goal 明示),先把机制打通,精度以后再迭代(可换更强模型或多模态复核)。默认关避免无谓截帧开销。

**Alternatives。**
- *多模态 LLM 直接吃帧:* token 爆炸、适配面窄、违「省 token」。否决。
- *固定间隔截全帧插入:* 噪声多、与内容脱钩、产物膨胀。否决。
- *全程视频喂 LLM:* 不可行。否决。
- *截图存储用 base64 内嵌 vs 文件 + 相对路径:* 见 Open Questions,倾向相对路径以保 md 可移植性。

### D5. MinerU 集成:可选构建层 + CPU pipeline + 外部 endpoint 扩展位

**决策。** MinerU 作为 **Dockerfile 可选层**(构建 ARG `ENABLE_MINERU`,默认 `0`,不进镜像以控体积);启用后以 **CPU pipeline 模式**本地执行。`pdf_reference/` 抽象 `PdfReferenceProvider`,两实现:`PypdfProvider`(默认,复用基底 `parsers/pdf_parser.py` + 章节大纲识别)与 `MineruProvider`(公式→LaTeX、表格→HTML、版面阅读顺序还原);外加 `ExternalMineruProvider`(HTTP endpoint 扩展位,配置存在时转发、否则回退本地 CPU)。设置页二选一(pypdf / MinerU),默认 pypdf;切换仅对新任务生效,不回溯历史。

**理由。** MinerU 依赖重(torch / opencv 等),默认装进镜像会把基础体积从几百 MB 撑到数 GB、拖慢构建与启动,与「个人本地开箱即用」相悖;把它做成可选层,「需要 PDF 公式/表格结构化」的用户显式开启即可。v1 无 GPU,CPU pipeline 是唯一合规执行模式;外部 endpoint 给未来「自建 GPU MinerU 服务」留接入点,接口先占位、配置缺省时自动回退本地。pypdf 作为默认方案,复用基底已验证的 PDF 解析与 `pdf_structure_analysis` prompt,零增量依赖、零增量风险。

**Alternatives。**
- *默认装 MinerU:* 镜像臃肿、启动慢,对不需要 PDF 的用户是纯负担。否决。
- *不引入 MinerU,只保留 pypdf:* 失去公式 / 表格 / 多栏版面的结构化能力,讲义对照质量打折。作为可选保留。
- *MinerU GPU / vLLM 引擎:* 违反「无 GPU」约束。否决(仅经 external endpoint 间接可用)。

### D6. ai_srt2md fork 改造边界:保留「内核」,重写「输入端 + 编排层」,新增「集成层」

**决策。** 把基底代码分三类处理:

| 类别 | 处理 | 具体模块 |
|---|---|---|
| **内核(原样复用)** | 保留,只做适配性微调 | `llm/`(8 家适配 + factory)、`prompts/`(全部 prompt)、`core/simple_processor.py`(SRT→笔记)、`core/aligner.py`、`core/filter.py`、`core/generator.py`、`parsers/srt_parser.py`、`utils/security.py` + `core/security_constants.py`(注入防护)、`utils/srt_validator.py`、思维导图导出、`db/task_repository.py` |
| **改造** | 接口换头或换实现 | 输入入口(「上传 SRT」→「视频链接 / 本地音视频」)、流水线编排(线性 `tasks/pipeline.py` → 6 步 DAG)、`parsers/pdf_parser.py`(扩成 `PdfReferenceProvider` 两方案)、前端视觉(套原型,见 D7)、`docker-compose.yml`(双容器 → 单容器,见 D1) |
| **新增** | 全新模块 | `media_ingest/`(yt-dlp 下载 + ffmpeg 提取 + 来源识别)、`speech_to_text/`(AsrEngine 抽象 + 3 实现 + VAD)、`screenshot/`([IMG:ts] 解析 + 截帧)、`pdf_reference/mineru_provider.py`、`pipeline/dag.py`(6 步状态机 + 节点级重跑)、`retention/`(五类保留策略 + 自动清理)、SSE 推送层 |

**理由。** 基底最有价值、最易出错的部分是「LLM 多厂商适配 + SRT→笔记 prompt 工程 + 注入防护」,这些已经过实战验证,**重写是纯损失**。把它们当稳定内核复用,把工程精力集中在 v1 的真正新价值上:把输入端从「字幕文件」前移到「视频」,以及把线性流程升级为可观测、可重跑的 DAG。这条边界也让「fork」名副其实——`git remote` 指向 ai_srt2md,后续若上游有 LLM/prompt 修复,可选择性 cherry-pick。

**Alternatives。**
- *全新重写:* 浪费已验证的 LLM 适配与 prompt 工程,延长交付、引入回归。否决。
- *最小改动,把 ASR 产物当 SRT 上传(沿用基底上传入口):* 失去「粘链接全自动」的核心价值,且无法做 DAG / 节点重跑。否决。
- *保留基底双容器形态:* 违反 D1 的单容器同源要求。否决。

### D7. 前端:Vue3 骨架保留,以 6 页高保真原型为视觉规约重建组件

**决策。** 复用基底 `frontend/src/` 的工程骨架(router / stores / `api/index.js` 对接模式 / 构建链),但把现有 `Home.vue` / `Settings.vue` 两个视图,按 `前端模板设计/59ade7a1-.../` 下的 **6 个高保真 HTML 原型**(console / task-detail / note / mindmap / history / settings)重建为 Vue 组件。原型的 `css/app.css` 抽取为设计 token(配色 / 间距 / 组件样式),复刻原型里的交互态(任务卡片、DAG 进度条、明暗主题切换、ASR/LLM 引擎状态卡)。新增对 SSE 进度流、任务创建(粘链接 / 上传音视频 / 附 PDF)、历史筛选、设置(ASR 引擎 / bilibili cookie / 保留策略 / 截图开关 / PDF 方案)的 API 对接。

**理由。** 原型已经把「产品长什么样」定义清楚(含配色、布局、组件、交互态),直接当视觉规约最省事;但它只是静态 HTML,没有路由 / 状态 / API 对接,无法直接当产物。基底的 Vue3 骨架恰好补上工程化那一半。两者拼接 = 原型的皮 + Vue 骨架的骨,既不脱离既定视觉,又不丢失工程能力。

**Alternatives。**
- *直接把静态 HTML 当前端:* 无路由 / 无状态 / 无 API 对接,不可用。否决。
- *脱离原型全量重设计 Vue:* 放弃已定稿的视觉,与产品意图相悖。否决。
- *在基底现有 Home/Settings 上小修小补:* 达不到原型的高保真度,且页数从 2 → 6。否决。

### D8. 并发队列与节点级重跑:复用 TaskQueue + 6 步 DAG 状态机

**决策。** 复用基底 `core/task_queue.py` 的 `max_concurrent` 参数,默认 **1**,设置页可调 **1~3**。流水线建模为 6 步 DAG(`pipeline/dag.py`),每个节点独立状态机:`pending / running / done / failed / skipped`(本地音视频来源跳过下载/提取记 `skipped`)。**节点级重跑**:用户可指定从某节点(如 ASR)重新执行,上游已 `done` 的产物(如已下载视频)直接复用、不重跑;重跑节点下游级联重算。每次节点状态变化先落 SQLite 再推 SSE(见 D10)。并发同时作用于「跨任务」(队列层)与「单任务内 VAD 分段」(D3)两层,二者共享一个可配的 CPU/IO 并发预算上限,避免本地资源争抢。

**理由。** 基底的 `TaskQueue` 已支持 `max_concurrent`,没必要重造并发控制。DAG 化的真正收益是**节点级重跑**:ASR 因网络抖动失败时,不必把已下载的几 GB 视频再下一遍;笔记不满意时,不必重跑 ASR。默认并发 1 是因为本地自用、无 GPU,whisper.cpp + MinerU 都吃 CPU,高并发只会互相抢资源;给到 1~3 的可调范围足够应对「同时粘几条短视频」的场景。

**Alternatives。**
- *整任务级重跑(失败从头):* 浪费已成功步骤的产物与时间,长视频场景体验极差。否决。
- *线性流水线、不支持节点重跑:* 退化为基底形态,失去 v1 核心可观测/可恢复价值。否决。
- *默认高并发(如 3):* 本地无 GPU 下 CPU 争抢严重、易 OOM。设默认 1、上限可调更稳。

### D9. 产物保留与自动清理:五类各自独立策略 + 定时扫描 + 启动清理

**决策。** 五类产物(视频 / 音频 / SRT / 笔记 / 截图)各自独立可配,取值限定 `permanent / 7d / 30d`,存 SQLite。产物按类型分目录落盘于命名 volume:`videos/`、`audio/`、`srt/`、`notes/`、`screenshots/`,临时 / 中间文件(下载分片、音频切片、ASR 中间结果)一律隔离到独立的 `temp/`,不污染产物目录。清理走**周期性扫描 + 启动时扫描**,无手动按钮;扫描跳过未达终态(排队 / 运行中)任务的产物;`permanent` 永不删;删除后同步更新 SQLite 产物引用,历史不再指向已删文件。提供存储用量统计接口(总量 + 按类型 + 按 Top 任务),设置 / 存储页展示。

**理由。** 个人本地磁盘有限,而五类产物的「价值 / 体积比」差异巨大:视频 / 音频动辄数百 MB ~ 数 GB 且可由链接重获,该短期清;笔记 / 思维导图是最终成果、KB 级,该永久留;SRT / 截图居中。**单一全局保留期**无法兼顾这种差异,必须分类型独立配。自动清理(定时 + 启动)比「手动点按钮」可靠——个人自用场景下用户不会记得点。临时文件隔离是为了让清理逻辑简单确定(只扫五类产物目录),也让产物目录干净可统计。

**Alternatives。**
- *全局单一保留期:* 灵活性不足,要么误删笔记、要么堆积大视频。否决。
- *手动清理按钮:* 易被遗忘,违 spec「无需用户干预」。否决。
- *扁平目录(不分类):* 难按类型统计 / 清理,且清理逻辑复杂。否决。

### D10. SSE 实时进度推送:FastAPI SSE + 节点状态先落库再推

**决策。** 后端用 `sse-starlette`(或 `StreamingResponse` 手搓)暴露 `/api/v1/tasks/{id}/stream` SSE 端点;事件类型覆盖节点状态变化、进度百分比、日志行、降级事件(D2)。每次节点状态变化,**先写 SQLite(节点状态 + 产物引用 + 时间戳),再向该任务的订阅者推 SSE**。前端用原生 `EventSource` 订阅,断线自动重连。启动时扫库,把残留的 `running` 任务标记为 `failed`(可重跑),避免「界面显示运行中但后端无进程」的悬空态。

**理由。** 本地自用、单向状态推送,SSE 是最简方案:浏览器原生支持(`EventSource`)、无需双向、比 WebSocket 轻量、比轮询延迟低且不浪费请求。**「先落库再推」**这一顺序是关键——SSE 是瞬态的(刷新 / 重启即丢),SQLite 是持久态,把权威状态放库里,SSE 只是「库变了就喊一声」,于是刷新页面 / 容器重启后前端重新查库就能恢复正确状态,与 spec「运行中任务重启后不悬空」对齐。

**Alternatives。**
- *WebSocket:* 双向能力对纯推送场景是多余的,且实现 / 运维更重。否决。
- *HTTP 轮询:* 延迟高、无谓请求多、降级事件难实时呈现。否决。
- *只查库、不做推送:* 体验差(用户需手动刷新看进度)。否决。

---

## Risks / Trade-offs

- **[风险] 在线 bcut 不稳定 / 限流(429)/ 协议变化** → [缓解] whisper.cpp 本地兜底(D2「在线优先」自动降级)+ external endpoint 扩展位 + 每次降级结构化日志 + 「指定单一引擎」逃生口。
- **[风险] whisper.cpp CPU 转录长音频极慢(数倍实时)** → [缓解] VAD 切分并行(D3)+ int8 量化 + 默认走在线 bcut,本地仅兜底;并在任务详情页暴露预估进度。
- **[风险] bilibili cookie 失效 / 触发风控** → [缓解] 失效识别为「登录态错误」并明确提示重粘;未配置时降级免登录画质并提示;cookie 仅用于 bilibili 来源、不外泄到其他平台下载请求。
- **[风险] MinerU CPU pipeline 慢且镜像大** → [缓解] 可选构建层默认不进镜像(D5);外部 endpoint 扩展位;默认走 pypdf。
- **[风险] `[IMG:ts]` 标记位置不准 / 滥用 / 越界时间戳** → [缓解] 默认关;后端对非法 ts 容错跳过并记日志;Non-goal 已声明 v1 接受猜测精度,以后换更强模型或多模态复核。
- **[风险] 单容器 FastAPI 同时扛静态托管 + 长任务 + 大文件上传** → [缓解] 个人自用低并发(默认 1)、上传走流式落盘、临时文件隔离(`temp/`);单进程瓶颈在 v1 量级不会暴露,留作以后观测。
- **[风险] yt-dlp 平台规则变化导致下载失败** → [缓解] 失败归类(链接无效 / 需登录 / 网络 / 风控 / 工具缺失)给中文可读错误;干净临时工作区重试不残留半成品;镜像内 yt-dlp 可随版本升级。
- **[风险] 容器重启时运行中任务悬空** → [缓解] 启动时扫 SQLite,`running` → `failed`(可重跑);节点级重跑(D8)让恢复代价低。
- **[风险] SQLite 多写并发(corruption / lock)** → [缓解] 默认并发 1(D8)天然降压;启用 WAL 模式;写路径集中在 `task_repository.py`。个人自用量级下不是问题,但需显式开 WAL。
- **[Trade-off] 默认单并发 = 吞吐低**:换稳定性与 CPU 友好;用户可手动调到 3。

---

## Migration Plan

从 ai_srt2md fork 到 vid2note v1 可用,分阶段(每阶段可独立验证):

1. **Fork 与清场。** 把 ai_srt2md fork 为 vid2note 仓库;清掉示例 SRT / 测试数据 / 无关 README;调整 `.env.example`、`requirements.txt` 起点。验证:`git remote -v` 能看到上游,基础镜像仍可构建。
2. **内核隔离。** 把 D6 表中的「内核」模块收敛到稳定的内部包边界(如 `core/kernel/`),明确对外接口,使后续改造不污染内核。验证:内核单元测试(基底已有 `backend/tests/`)全绿。
3. **DAG 编排层(D8 / D10)。** 新建 `pipeline/dag.py`(6 步状态机 + 节点级重跑)+ SSE 推送层;先把「下载/提取」做成 no-op、「ASR」直接读用户上传的 SRT(临时桥),让 DAG 与 SSE 先跑通。验证:粘一个本地 SRT,前端能看到 6 步进度推送与节点状态。
4. **输入端前移(D6 改造)。** API 从「上传 SRT」改为「视频链接 / 本地音视频」+ 来源识别;实现 `media_ingest/`(yt-dlp 整段最高画质 + bilibili cookie 降级 + ffmpeg 提取)。验证:YouTube / Bilibili / 直链 / 本地音视频四类输入分别走对跳过逻辑。
5. **ASR 层(D2 / D3)。** 实现 `AsrEngine` 抽象 + bcut / whisper.cpp / external 三实现 + 在线优先降级 + VAD 切分并行与时间戳拼回;删除第 3 步的临时 SRT 桥。验证:短音频不分段、长音频分段拼回时间戳单调;断网时自动降级 whisper.cpp。
6. **笔记 + 截图(D4)。** 复用 `SimpleProcessor` + prompt 库;实现 `[IMG:ts]` 标记解析与 ffmpeg 截帧替换(默认关);接 MinerU 可选层(D5)。验证:开 / 关截图两种产物对比;带 PDF 讲义时笔记按章节对齐。
7. **保留与清理(D9)。** 五类产物分目录 + 独立策略 + 定时 / 启动扫描 + 存储统计接口。验证:把系统时钟注入快进,验证过期删除与 permanent 不删;`docker compose down`(不带 `-v`)再 up 数据与产物在。
8. **前端重建(D7)。** 按 6 页原型把 Vue 视图重建,接 SSE / 任务 / 设置 / 历史 API。验证:6 页视觉与原型对齐,DAG 进度与降级提示实时呈现。
9. **单容器化(D1)。** 合并 Nginx 静态托管进 FastAPI `StaticFiles`,改单 Dockerfile + 单服务 compose;MinerU 可选构建层。验证:`docker compose up` 后 `localhost:8765` 同源前后端可达,镜像 `docker history` 无明文密钥。
10. **端到端冒烟。** 三来源(YouTube / Bilibili / 本地视频)× 两 PDF 模式(pypdf / MinerU)× 开关截图,跑通完整六步;验证产物落盘、保留策略、SSE、节点重跑、重启不悬空。

---

## Open Questions

1. **whisper.cpp 集成形态:** 调预编译二进制(镜像小、依赖少)还是 Python 绑定 `faster-whisper`(API 顺、但带 ONNX/Torch 依赖)?需在 arm64 CPU 上实测体积与速度后定。
2. **在线 ASR 默认引擎:** 选择 `bcut` 作为实验性默认 provider，并以本地引擎提供可用性兜底。
3. **VAD 工具选型:** `silero-vad`(轻、准、Torch 依赖)vs `webrtcvad`(极轻、准度一般)vs whisper.cpp 内置 VAD?与 Q1 的依赖策略一并定。
4. **截图存储形态:** base64 内嵌 md(单文件自包含、但 md 膨胀且不可移植到无图环境)vs volume 内文件 + 相对路径(md 轻盈可移植、但离开 volume 看不到图)?倾向相对路径,待确认导出语义。
5. **任务内 vs 跨任务并发预算:** 默认跨任务并发 1 时,VAD 分段并行是否仍开?两层共享一个 CPU 上限还是独立?需在 D8 并发实现时实测。
6. **MinerU 外部 endpoint 协议:** 复用 MinerU 官方 HTTP API 形态(文件上传 + JSON 返回 markdown)还是自定义?需在 D5 扩展位落地前定契约。
7. **历史页范围:** 原型 `history.html` 有筛选 / 计数;v1 是否需要搜索 / 分页,还是仅按时间倒序列表?待确认。
8. **bilibili cookie 存储:** 明文存 SQLite(个人本地自用、无登录)是否可接受,还是做最低限度加密?需确认威胁模型(本机无第二用户的前提)。
9. **SRT 校验复用边界:** 基底 `srt_validator.py` 用于「用户上传 SRT」校验;v1 SRT 由 ASR 生成,拼回后的单调化校验是否直接复用该工具,还是需扩展(如允许段间微小重叠容差)?
