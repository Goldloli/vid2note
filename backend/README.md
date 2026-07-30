# vid2note 后端

FastAPI 后端负责媒体输入、六步 DAG、SQLite 持久化、SSE、LLM/ASR Provider 和前端静态资源托管。

公开 API 使用 `/api/v1` 前缀；交互式文档位于 `/docs`。

## 开发

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
SERVER_HOST=127.0.0.1 .venv/bin/python run.py
```

测试：

```bash
.venv/bin/python -m pytest
.venv/bin/python -m pip_audit -r requirements.txt
```

不要使用旧的 `src.api.upload/process/queue` 路由开发新功能；v1 入口集中在 `src/api/v1/`。新增模块通过 `src.core.kernel` 门面使用继承自 `ai_srt2md` 的内核。

架构、扩展点和数据流见 [项目架构文档](../docs/ARCHITECTURE.md)，接口和数据模型约定见 [CONTRACT.md](CONTRACT.md)。
