# 贡献指南

## 开发环境

```bash
# Python 后端
python3.11 -m venv .venv
.venv/bin/pip install -e "./core[local-asr,dev]" -e "./server[dev]"

# 前端
cd desktop && npm install
```

## 常用命令

```bash
make test          # 后端测试 + coverage
make lint          # ruff check + format
make typecheck     # mypy
make dev           # 启动后端开发服务器
make desktop-dev   # 启动 Electron 开发
make e2e           # Playwright E2E
make docker-up     # Docker 启动
```

## 测试规范

- 后端：`core/tests/` + `server/tests/`，pytest + coverage ≥ 75%
- 外部依赖（torch/ffmpeg/yt-dlp）必须 mock，CI 环境不安装
- ASR/LLM 测试用注入工厂模式，不依赖真实 API Key
- E2E：`desktop/tests/e2e/`，Playwright，数据隔离到临时目录

## 提交规范

```
feat: 新功能
fix: 修复
refactor: 重构
docs: 文档
test: 测试
chore: 构建/工具
```

## CI

- `.github/workflows/ci.yml`：push/PR 时运行 3 jobs（test-python + lint + test-frontend）
- `.github/workflows/release.yml`：打 `v*` tag 时构建 macOS .dmg + Docker 并发布 Release
