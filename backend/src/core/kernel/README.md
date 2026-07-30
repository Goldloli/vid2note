# vid2note 内核边界(Kernel)

本目录是 vid2note 对基底 ai_srt2md「原样复用」内核的**统一对外门面**。
详见 `openspec/changes/build-vid2note-v1/design.md` 的 **D6(fork 改造边界)**。

## 规矩

- v1 新增模块(`media_ingest` / `speech_to_text` / `screenshot` / `pipeline/dag` / `retention` / SSE 层)**必须**从 `core.kernel` 导入内核能力。
- **不得**直接穿透内核内部(如 `from src.core.simple_processor import ...`、`from src.llm.xxx import ...`)。
- 内核模块本身保持基底位置,**不做物理移动** —— 零迁移风险,便于上游 cherry-pick。

## 内核范围(design D6「原样复用」)

| 能力 | 位置 |
|---|---|
| LLM 8 家适配 + factory | `llm/`(`BaseLLM`、`LLMFactory`) |
| prompt 库 | `prompts/` |
| 字幕→笔记 + 思维导图 | `core/simple_processor.py`(`SimpleProcessor`) |
| 语义对齐 / 内容过滤 / MD 生成 | `core/{aligner,filter,generator}.py` |
| SRT / PDF 解析 | `parsers/` |
| SQLite 持久化 | `db/`(`Database`、`TaskRepository`) |
| 安全防护 / SRT 校验 | `utils/security.py`、`core/security_constants.py`、`utils/srt_validator.py` |
| 日志 | `utils/logger.py` |

## 改造 / 新增(在内核门外)

- 输入端(视频链接 / 本地音视频)→ `media_ingest/`(新)
- ASR → `speech_to_text/`(新)
- 截图嵌入 → `screenshot/`(新)
- PDF 基础文本提取 → 复用内核 `parsers/pdf_parser.py`;MinerU/OCR 属于 Roadmap
- DAG 编排 → `pipeline/dag.py`(新,复用内核 `TaskQueue` 但在其上加六步状态机)
- 保留清理 → `retention/`(新)
- SSE 推送 → 新增层
- 前端 Vue3 套原型、Docker 单容器化 → 改造
