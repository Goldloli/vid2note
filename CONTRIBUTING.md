# 参与贡献

感谢你愿意改进 vid2note。开始编码前，请先搜索现有 Issue；较大的功能或行为变更建议先开 Discussion 或 Feature Request，确认方向后再实现。

## 开发环境

要求：

- Python 3.11
- Node.js 22+
- FFmpeg
- Docker 及 Docker Compose（用于完整部署验证）

后端：

```bash
python3.11 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cd backend
.venv/bin/python -m pytest
```

前端：

```bash
cd frontend
npm ci
npm run check
```

浏览器端到端测试是可选门禁，依赖单独安装：

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-e2e.txt
backend/.venv/bin/python -m playwright install chromium
backend/.venv/bin/python backend/tests/test_playwright.py
```

提交前还应运行发布预检；它会扫描当前文件和可达 Git 历史，但不会输出凭据原文：

```bash
python3 scripts/release_preflight.py
```

本地联调：

```bash
# 终端 1
cd backend
SERVER_HOST=127.0.0.1 .venv/bin/python run.py

# 终端 2
cd frontend
npm run dev
```

浏览器访问 `http://localhost:5735`；Vite 会把 `/api` 代理到后端 `:8765`。

## 代码约定

- 后端使用 `from src.xxx` 导入；v1 模块通过 `src.core.kernel` 门面使用继承自 `ai_srt2md` 的内核。
- 用户输入、上传文件、外部 URL 和密钥处理必须有明确的校验及失败行为。
- 新功能需要测试；Bug 修复应先增加能复现问题的回归测试。
- 不要提交 `.env`、`data/`、模型、Cookie、API Key 或构建产物。
- 前端遵循 `DESIGN.md`：清晰普通版、实色卡片、标准组件，不引入玻璃和不必要的动效。

## 提交 Pull Request

1. 从 `main` 创建功能分支。
2. 保持 PR 聚焦，不混入无关格式化。
3. 更新受影响的文档和 `CHANGELOG.md` 的 `Unreleased` 部分。
4. 确保后端测试与依赖审计、前端 check 与依赖审计、发布预检、Docker 构建通过。
5. 在 PR 描述中说明动机、验证方法、兼容性和安全影响。

提交信息推荐使用简洁的 Conventional Commits 风格，例如：

```text
feat(llm): add an OpenAI-compatible provider
fix(upload): reject oversized media files
docs: clarify Docker networking
```

## 扩展 Provider

LLM、ASR 和流水线扩展点见 [架构文档](docs/ARCHITECTURE.md)。新增 Provider 时不要在 UI、运行时和工厂中分别维护不同的能力列表。

参与项目即表示你同意以本项目的 MIT License 提交你的贡献。
