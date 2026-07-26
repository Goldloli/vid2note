## Why

看视频做笔记是高频却耗时的场景:手动下载、提取音频、转字幕、整理成结构化笔记,流程冗长割裂。vid2note 把这条链路自动化为一个本地流水线 —— 粘贴视频链接,自动跑通「下载 → 提取音频 → 转录 → LLM 整理笔记 → 思维导图」,直接产出可用的 Markdown 笔记 + 思维导图。以作者自有的 ai_srt2md(字幕→笔记,已是 FastAPI:8765 + Vue3)为基底改造,大幅缩短从零到可用的距离;第一版用 Docker 部署,本地开箱即用。

## What Changes

新建 vid2note v1 —— Docker 部署的本地 Web 应用(浏览器访问 localhost:8765)。相对基底 ai_srt2md:

**复用 ai_srt2md 现有能力(改造集成):**
- FastAPI 后端(:8765)、SQLite 持久化、异步任务队列
- LLM 适配层(7 家 + Ollama = 8 家,OpenAI 兼容)、prompt 库、提示词注入防护、SRT 校验
- 字幕→笔记核心流程(`SimpleProcessor`)、PDF 讲义对照(pypdf 分支)、思维导图(XMind/PNG)
- Vue3 前端骨架与 API 对接

**新增能力:**
- 视频下载层:yt-dlp 下载整段高清视频(YouTube/Bilibili/直链),bilibili 支持 cookie(设置页粘贴 `SESSDATA`/`bili_jct`/`DedeUserID`)
- 音频提取:ffmpeg 从视频提取音轨
- ASR 转录层(取代 ai_srt2md「用户上传字幕」的输入方式):在线 AsrTools(剪映/必剪)优先 + 本地 whisper.cpp(CPU + int8)兜底;长音频 VAD 切片并行 + 时间戳偏移拼回;留「外部 ASR endpoint」扩展位
- 截图嵌入 md(可开关,默认关):开启时字幕带时间戳喂 LLM,LLM 标记 `[IMG:ts]`,后端截视频对应帧插入笔记
- PDF 拆解增强:新增 MinerU 版面结构化拆解方案(与现有 pypdf 并列,设置可选)
- 任务流水线可视化:6 步 DAG、SSE 实时进度、节点级失败重跑、并发队列(1~3 可配,默认 1)
- 产物保留策略:每种产物(视频/音频/SRT/笔记/截图)各自独立可配 永久 / 7 天 / 30 天
- Docker 化部署:`docker compose up` 一条命令起来

**改造:**
- 前端 UI 从 ai_srt2md 现有界面换成高保真原型设计(主控台 / 任务详情 / 笔记 / 思维导图 / 历史 / 设置 6 页)
- 输入入口从「上传 SRT」改为「粘贴视频链接 / 上传本地视频」

### Non-goals(v1 不做,留待以后版本)
- Electron 桌面客户端(及配套扫码登录)
- 远程访问 / 多用户 / 账号鉴权
- GPU / MLX 加速(本地 ASR 与 MinerU 均走 CPU;仅留「外部服务 endpoint」扩展位)
- 交互式思维导图页(v1 仅导出 xmind/png/md)
- 平台官方字幕(CC)抓取与切换分支(v1 一律走 ASR)
- MinerU 的 vLLM / GPU 高精度引擎

## Capabilities

### New Capabilities
- `media-ingest`: 视频下载(yt-dlp,整段高清,bilibili cookie)+ 音频提取(ffmpeg)
- `speech-to-text`: ASR 转录(在线 AsrTools 优先 / 本地 whisper.cpp 兜底 / 外部 endpoint 扩展;长音频 VAD 切片并行 + 时间戳偏移拼回)
- `note-generation`: 字幕 → 结构化 Markdown 笔记(LLM 整理,纯文本喂省 token,8 家适配);含可选截图嵌入(开关,LLM 驱动)
- `pdf-reference`: PDF 讲义对照(简单 pypdf / MinerU 版面拆解两方案,设置可选)
- `mindmap-export`: 思维导图导出(xmind / png / md 大纲)
- `task-pipeline`: 六步流水线编排、状态机、SSE 实时进度、并发队列(1~3)、节点级失败重跑、历史与筛选
- `storage-retention`: SQLite + 文件存储;各产物独立保留策略(永久/7天/30天)+ 自动清理
- `web-frontend`: Vue3 前端改造,套用高保真原型 6 页
- `docker-deployment`: docker compose 编排、镜像构建、volume 持久化

### Modified Capabilities
(无 —— 本项目为全新基线,首次建立上述 specs)

## Impact

- **代码**:fork ai_srt2md 为仓库基底;新增下载 / ASR / 截图 / MinerU 集成 / 流水线编排 / Docker 等模块;前端 Vue3 视觉重构
- **依赖**:新增 yt-dlp、ffmpeg、AsrTools(bk_asr)、whisper.cpp(binary 或绑定)、MinerU(重,torch/opencv 等)
- **外部系统**:bilibili / YouTube(经 yt-dlp)、剪映/必剪 ASR 接口、DeepSeek 等 LLM API
- **运行环境**:Docker(macOS arm64 优先,CPU);SQLite + 本地 volume
- **API**:在 ai_srt2md 现有 HTTP API(:8765)上扩展(任务创建接受视频链接、流水线状态/日志 SSE、设置、历史等)
