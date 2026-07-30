# 项目 AI 代理指引

本文件为在本项目中工作的 AI 编码代理提供说明与上下文。

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:6cd5cc61 -->
## Beads 任务追踪器

本项目使用 **bd (beads)** 做任务追踪。运行 `bd prime` 可查看完整的工作流上下文与命令。

### 快速参考

```bash
bd ready                # 查找可做的任务
bd show <id>            # 查看任务详情
bd update <id> --claim  # 认领任务
bd close <id>           # 完成任务
```

### 规则

- 用 `bd` 做所有任务追踪 —— **不要**使用 TodoWrite、TaskCreate 或 markdown TODO 列表
- 运行 `bd prime` 获取详细命令参考与会话收尾协议
- 用 `bd remember` 保存持久知识 —— **不要**使用 MEMORY.md 文件

**架构一句话：** 任务数据存在本地 Dolt 数据库；跨机同步走 git 远端的 `refs/dolt/data`；`.beads/issues.jsonl` 只是被动导出。详见 https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md（含反模式说明）。

## 代理上下文档位

beads 管理区块只是任务追踪指引，不构成对仓库、用户或编排器指令的覆盖授权。

- **保守档（默认）：** 用 `bd` 做任务追踪。除非被明确要求，不要执行 git commit、git push 或 Dolt 远端同步。交接时报告改动的文件、校验结果与建议的下一步命令。
- **精简档：** 工具指令文件只作为指向 `bd prime` 的指针；除非有活动指令另行规定，沿用与保守档相同的 git 策略。
- **团队维护档：** 仅当仓库明确开启时，代理方可关闭 beads、跑质量门禁、提交并推送，作为会话收尾的一部分。当前如有"不要提交/不要推送"的指令，仍以该指令为准。

## 会话收尾

本协议适用于结束一次 beads 实现工作流时，服从于明确的用户、仓库与编排器指令。

1. **为剩余工作建任务** —— 为任何需要跟进的事项创建 beads
2. **跑质量门禁**（若改动过代码）—— 测试、lint、构建
3. **更新任务状态** —— 关闭完成项、更新进行中项
4. **按当前档位处理 git/同步：**
   ```bash
   # 保守/精简/默认：报告状态与拟执行命令；等待批准。
   git status

   # 仅团队维护档开启时（且当前指令不禁止）：
   git pull --rebase
   git push
   git status
   ```
5. **交接** —— 汇总改动、校验、任务状态，以及任何被阻塞的同步/提交/推送步骤

**关键规则：**
- 明确的用户或编排器指令优先于本 beads 区块。
- 未经当前档位或当前用户请求明确授权，不要提交或推送。
- 若某项必需的同步或推送被阻塞，停下并报告确切的命令与错误。
<!-- END BEADS INTEGRATION -->


## 项目架构与技术约定(沉淀自 openspec)

> **vid2note**:视频链接 / 本地文件 → Markdown 笔记 + 思维导图的**本地 Docker Web 应用**(`:8761`),个人自用,无登录。

### 技术栈
- **后端**:Python 3 + FastAPI(容器内 `:8765`,宿主映射 `:8761`)。基底 **fork 自 ai_srt2md**,内核原样复用:LLM 8 家适配 / prompt 库 / `SimpleProcessor`(字幕→笔记) / 注入防护 / SRT 校验 / 思维导图导出 / SQLite
- **前端**:Vue3 + Vite(清晰普通版:实色卡片 + 标准组件,详见 `DESIGN.md`)
- **部署**:Docker 单容器(`docker compose up`,FastAPI 同源托管 API + 前端静态)

### 六步流水线
`下载(yt-dlp 整段高清,bilibili 带 cookie)→ 提取音频(ffmpeg)→ ASR(实验性在线 bcut 优先 / 本地 whisper.cpp 兜底,长音频 VAD 切片并行)→ LLM 笔记(纯文本喂,默认 DeepSeek deepseek-v4-flash,8 家适配)→ 思维导图(xmind/png/md)→ 清理(按保留策略)`

### 关键架构决策(摘自 design D1–D10)
- **D1 单容器**:弃双容器,FastAPI 同源托管前后端,`:8761` 一端口
- **D2 ASR 抽象**:`AsrEngine` 接口 + bcut(实验性在线)/ whisper.cpp(本地 CPU int8)/ external(扩展位),在线优先降级
- **D3 VAD 切片并行**:长音频按静音切分并行转录 + 时间戳偏移拼回单调 SRT
- **D4 截图嵌入**:LLM 标记 `[IMG:ts]`,后端 ffmpeg 截帧(默认关)
- **D5 MinerU 可选**:PDF 拆解,默认 pypdf,MinerU 可选构建层(`ENABLE_MINERU`)
- **D6 fork 内核复用**:ai_srt2md 内核原样复用,改造输入端(视频链接)+ 编排(DAG)+ 前端
- **D8 并发**:1–3 可配 + 节点级重跑(复用上游产物)
- **D9 retention**:五类产物(视频/音频/SRT/笔记/截图)各自独立保留(permanent/7d/30d)
- **D10 SSE**:节点状态「先落 SQLite 再推 SSE」,容器重启不悬空

### 能力域(openspec 9 capability,specs 在 `openspec/specs/`)
`media-ingest`(下载)/ `speech-to-text`(ASR)/ `note-generation`(笔记+截图)/ `pdf-reference`(PDF 对照)/ `mindmap-export`(导图)/ `task-pipeline`(六步 DAG + SSE + 并发 + 重跑 + 历史)/ `storage-retention`(存储 + 保留)/ `web-frontend`(前端)/ `docker-deployment`(部署)

### 开发约定
- **import**:`from src.xxx`(`src` 是包,`backend` 在 PYTHONPATH;基底 `simple_processor` 用 relative `from ..prompts`,要求 src 作包)
- **内核门面**:`from src.core.kernel import SimpleProcessor, LLMFactory, TaskQueue, SRTParser, TaskRepository, ...` —— v1 新模块只从门面取内核,**不穿透内部**
- **测试**:`cd backend && .venv/bin/python -m pytest`(⚠️ 勿用 `source .venv/bin/activate`,会被 ai_srt2md 的 venv 干扰)
- **前端**:清晰普通版(实色卡片 + 标准组件),**无玻璃/渐变/inset/hover-scale**,遵循 `DESIGN.md`
- **任务追踪**:`bd`(beads),不用 TodoWrite/TaskCreate/markdown TODO;持久知识用 `bd remember`
- **git**:保守档(默认不 commit/push/Dolt sync,除非明确授权)

### 构建 / 测试 / 部署
```bash
# 后端测试(234+ 单测)
cd backend && .venv/bin/python -m pytest

# 前端构建
cd frontend && npm install && npm run build

# Docker 部署(:8761)
cp .env.example .env            # 填 DeepSeek key
docker compose up -d --build    # → http://localhost:8761

# 端到端(playwright,需容器运行 + 配好 ASR 模型/key)
cd backend && .venv/bin/python tests/test_playwright.py

# openspec
openspec list                   # active changes
ls openspec/specs/              # main capability specs
ls openspec/changes/archive/    # 已归档 change(build-vid2note-v1 / frontend-liquid-glass-redesign)
```

### 设计与规格文档
- **`DESIGN.md`**:前端清晰普通版设计系统(token + 组件库 + 布局 + 交互 + do/don't),后续页面开发遵循
- **`openspec/specs/`**:9 个 capability 的 main spec(功能要求 + 场景)
- **`openspec/changes/archive/`**:已归档 change 的 proposal/design/tasks(含 v1 完整决策与重构记录)
- **`backend/CONTRACT.md`**:后端改造契约(Task 模型字段 / 产物目录 / 路由 / pipeline 编排)
