<p align="center">
  <img src="frontend/public/icons/vid2note-icon-180.png" width="112" alt="vid2note icon">
</p>

<h1 align="center">vid2note</h1>

<p align="center">
  把视频链接或本地音视频变成结构化 Markdown 笔记与思维导图。
</p>

<p align="center">
  <a href="https://github.com/Goldloli/vid2note/actions/workflows/ci.yml"><img src="https://github.com/Goldloli/vid2note/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.11-3776AB" alt="Python 3.11">
  <img src="https://img.shields.io/badge/Vue-3-42b883" alt="Vue 3">
  <img src="https://img.shields.io/badge/Docker-ready-2496ED" alt="Docker ready">
</p>

<p align="center">
  <strong>中文</strong> · <a href="README_EN.md">English</a>
</p>

> [!IMPORTANT]
> vid2note 是无登录的本地单用户应用。Docker Compose 默认只监听
> `127.0.0.1:8761`。不要在没有认证、TLS 和访问控制的情况下直接暴露到公网。

## 能力

六步流水线：

```text
下载 → 提取音频 → ASR 转录 → LLM 生成笔记 → 思维导图 → 清理
```

- 支持 YouTube、Bilibili、普通 HTTP(S) 链接、本地视频和本地音频。
- 默认使用实验性 `bcut` 在线 ASR；可切换本地 whisper.cpp/faster-whisper 或自建 HTTP ASR。
- 支持 DeepSeek、Qwen、GLM、Moonshot、MiniMax、Doubao、Baidu、Ollama，以及自定义 OpenAI-compatible 服务。
- 设置中心按通用、LLM、笔记、存储、高级、关于分区；ASR 页面提供引擎、Whisper、外部服务与策略诊断。
- 笔记详细度提供简洁、适中、详细、超详细四档，并固化到每个任务。
- 可附带一份 PDF 讲义，以基础文本提取结果辅助笔记结构和术语。
- 可选按 LLM 标记截取视频关键帧并嵌入 Markdown。
- 导出 Markdown、XMind、PNG 和 Markdown 大纲。
- SQLite 持久化任务；支持 SSE 进度、失败节点重跑、批量导出和产物保留策略。
- 前后端同源、单容器部署。

当前能力边界与后续计划见 [Roadmap](docs/ROADMAP.md)。

## 快速开始

要求：

- Docker Engine / Docker Desktop
- Docker Compose v2
- 至少 2 GB 可用内存；本地 ASR 建议 4–8 GB，取决于模型

```bash
git clone https://github.com/Goldloli/vid2note.git
cd vid2note
cp .env.example .env
docker compose up -d --build
```

打开 <http://localhost:8761>，然后在“设置”页配置 LLM。

也可以在 `.env` 中填写默认 Provider 的 Key，例如：

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-key
DEEPSEEK_MODEL=deepseek-v4-flash
```

设置页保存的公开参数优先于环境变量；环境变量会为尚未保存的字段提供默认值。

查看状态：

```bash
docker compose ps
docker compose logs -f vid2note
curl http://localhost:8761/api/v1/health
```

停止或升级：

```bash
docker compose down
git pull --ff-only
docker compose up -d --build
```

`docker compose down` 不会删除 `./data`。升级前建议先备份：

```bash
docker compose stop
tar -czf vid2note-data-backup.tar.gz data
docker compose start
```

## 使用 Ollama

先在宿主机启动 Ollama 并准备模型：

```bash
ollama pull qwen3.5
```

修改 `.env`：

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3.5
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

然后重建容器，或在设置页选择 `ollama`。Ollama 不需要 API Key。Compose 已为 Linux 添加 `host.docker.internal` 映射。

## 本地 ASR

项目不会在运行时自动下载 Whisper 模型。使用本地 ASR 时，需要把 faster-whisper 模型目录或 whisper.cpp 模型文件挂载进容器，并在 ASR 页面填写容器内路径。

示例 `compose.override.yml`：

```yaml
services:
  vid2note:
    volumes:
      - ./models:/models:ro
```

随后把模型路径设置为 `/models/<模型目录或文件>`。在线优先策略会在 `bcut` 不可用时尝试本地模型；没有本地模型时会返回明确错误。

## 配置与数据

- 运行数据：`./data`
- SQLite：`./data/tasks.db`
- 公开设置：`./data/config/settings.json`
- 加密凭证：`./data/config/credentials.enc`
- 本地主密钥：`./data/config/master.key`
- 任务产物：`./data/videos`、`audio`、`srt`、`notes`、`screenshots`
- 配置入口：Web 设置页、`.env`
- API 文档：Docker 部署为 <http://localhost:8761/docs>；仅启动后端开发服务时为 <http://localhost:8765/docs>

完整环境变量、优先级和模型配置见 [配置文档](docs/CONFIGURATION.md)。

LLM Key、Bilibili Cookie 和外部 ASR Key 使用 Fernet 认证加密保存，不会写入 `settings.json` 或 API 的普通设置响应。`master.key` 与密文同属敏感备份；生产部署建议通过 `VID2NOTE_MASTER_KEY_FILE` 挂载 Docker Secret。不要共享 `data/`，也不要把它提交到 Git。

## 本地开发

后端：

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cd backend
SERVER_HOST=127.0.0.1 .venv/bin/python run.py
```

前端：

```bash
# 需要 Node.js 22+
cd frontend
npm ci
npm run dev
```

验证：

```bash
cd backend
.venv/bin/python -m pytest

cd ../frontend
npm run check

cd ..
docker compose build
```

更多实现细节见 [架构文档](docs/ARCHITECTURE.md) 和 [贡献指南](CONTRIBUTING.md)。

## 项目结构

```text
vid2note/
├── backend/             FastAPI、流水线、Provider、SQLite、测试
├── frontend/            Vue 3、Vite、Pinia
├── data/                本地数据库与产物（内容不入 Git）
├── docs/                架构、配置、故障排查、Roadmap
├── openspec/            当前能力规格与历史变更
├── .github/             CI、发布、依赖更新、社区模板
├── Dockerfile
└── docker-compose.yml
```

## 安全与合规

- 默认拒绝带凭证的下载 URL、localhost、内网和保留 IP；确有本地直链需求时可设置 `ALLOW_PRIVATE_URLS=true`。
- 媒体和 PDF 采用流式写入并有大小上限。
- LLM 生成的 Markdown 在浏览器渲染前会清洗 HTML。
- 服务端内部异常只写日志，500 响应不返回堆栈或原始错误。

`bcut` 是实验性在线兼容能力，依赖外部服务且不保证持续可用；视频平台可用性同样不由本项目保证。请遵守内容版权、网站服务条款和所在地区法律，只处理你有权使用的内容。

安全问题请按 [安全策略](SECURITY.md) 私下报告。

## 参与贡献

欢迎 Bug 修复、Provider、测试、文档和易用性改进。提交 PR 前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [行为准则](CODE_OF_CONDUCT.md)。

## 致谢与许可证

vid2note 由同一作者的 `ai_srt2md` 演进而来，继承其字幕解析、Prompt、LLM、笔记生成和思维导图内核，并新增视频输入、ASR、DAG、Web UI 和容器部署。详情见 [NOTICE](NOTICE)。

项目以 [MIT License](LICENSE) 开源。
