# vid2note

把视频链接 / 本地视频一键变成**结构化 Markdown 笔记 + 思维导图**的本地工具。
粘贴 YouTube / Bilibili / 直链,或拖入本地视频,自动跑通「下载 → 提取音频 → 转录 → LLM 整理笔记 → 思维导图」流水线。

> **v1 形态**:Docker 部署的 Web 应用(浏览器访问 `localhost:8765`),个人本地自用,无登录。
> 基底 fork 自 `ai_srt2md`(字幕→笔记),在其上新增视频下载 / ASR / 截图嵌入 / DAG 编排 / Docker 化。

## 能做什么

- **粘链接出笔记**:YouTube / Bilibili / 直链 / 本地音视频四类输入,自动跑六步流水线
- **ASR 转录**:在线 AsrTools(剪映/必剪)优先,本地 whisper.cpp(CPU)兜底;长音频 VAD 切片并行
- **LLM 整理笔记**:8 家大模型(默认 DeepSeek `deepseek-v4-flash`),纯文本喂省 token
- **截图嵌入**(可选):LLM 判断「需图」处自动截视频帧插入笔记
- **PDF 讲义对照**:简单 pypdf / MinerU 版面拆解两方案
- **思维导图**:导出 xmind / png / md 大纲
- **可观测可重跑**:六步 DAG 可视化、SSE 实时进度、节点级失败重跑
- **磁盘可控**:五类产物各自独立保留策略(永久 / 7 天 / 30 天)

## 快速开始(Docker,推荐)

```bash
cp .env.example .env          # 填入 LLM API Key(也可启动后在「设置」页填)
docker compose up -d --build
```

浏览器打开 `http://localhost:8765`。

## 本地开发

后端:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # http://localhost:8765/docs
```

前端:
```bash
cd frontend
npm install
npm run dev                   # http://localhost:5735
```

## 项目结构

```
vid2note/
├── backend/                  FastAPI 后端(:8765)
│   ├── src/   api/ core/ llm/ parsers/ prompts/ db/ models/ utils/ ...
│   ├── requirements.txt
│   └── run.py
├── frontend/                 Vue3 + Vite(六页:主控台/任务详情/笔记/思维导图/历史/设置)
├── config/                   本地配置(gitignored)
├── docs/                     TECHNICAL.md / PROMPTS.md
├── openspec/                 OpenSpec 规格(change: build-vid2note-v1)
├── 前端模板设计/              高保真 HTML 原型(设计稿,gitignored)
└── docker-compose.yml
```

## 规格与设计

详见 `openspec/changes/build-vid2note-v1/`(`proposal.md` / `specs/` / `design.md` / `tasks.md`)。

## License

MIT
