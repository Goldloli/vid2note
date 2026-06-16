# vid2note

视频链接 → Markdown 笔记 + 思维导图。基于 FastAPI + Vue3 + LLM。

## 快速开始

### Docker 部署（推荐）

```bash
# CPU 版本
docker compose up vid2note-cpu

# GPU 版本（需 nvidia-docker2）
docker compose up vid2note-gpu

# 带前端 Nginx
docker compose --profile web up
```

### 环境变量

复制 `.env.example` 为 `.env`，填入 API 密钥：

```bash
cp .env.example .env
```

### 本地开发

```bash
# 安装依赖
uv pip install -e "./core[local-asr,dev]" -e "./server[dev]"

# 运行测试
pytest core/tests/ server/tests/ -v

# 启动后端
uvicorn vid2note_server.main:app --reload

# 启动前端（开发模式）
cd desktop && npm install && npm run dev
```

### Electron 桌面应用

```bash
# 开发模式
cd desktop && npm run electron:dev

# 打包 macOS
python scripts/package_macos.py
```

## 架构

- `core/` - 纯 Python 业务库（无 FastAPI 依赖）
- `server/` - FastAPI HTTP 服务层
- `desktop/` - Electron + Vue3 桌面客户端
- `scripts/` - 打包和二进制管理脚本

## 流水线节点

1. **download** - 下载视频
2. **extract_audio** - 提取音频
3. **transcribe** - ASR 转录
4. **organize** - LLM 整理笔记
5. **mindmap** - 生成思维导图
6. **cleanup** - 清理临时文件

## 支持的平台

| 平台 | 方式 | ASR | LLM |
|------|------|-----|-----|
| macOS arm64 | Electron + 内置 Python | 本地/云端 | 云端/Ollama |
| Docker CPU | 容器 | 云端 | 云端 |
| Docker GPU | 容器 | 本地/云端 | 云端 |

## 许可证

MIT
