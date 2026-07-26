# vid2note 后端改造契约（CONTRACT.md）

> 本文件是 vid2note v1 后端（fork 自 ai_srt2md）**所有模块开发与整合的唯一统一约束**。
> 任何 Implement agent 在动 `backend/src` 前 MUST 先读本文件，并严格遵守本文定义的字段、目录、路由、DAG 数据流与模块接口签名。
> 上位依据：`openspec/changes/build-vid2note-v1/{proposal.md, design.md, specs/*/spec.md, tasks.md}`。spec 约束「做什么」，design 解释「为什么」，**本文锁定「怎么对接」**。
> 与本文件冲突时：spec > design > 本契约。发现冲突停下报告，不要擅自改本契约。

---

## 0. 总体原则（所有模块通用，必守）

1. **包与 import**：`src` 是包，运行入口为 `backend/` 下 `python run.py`。所有 import 写 `from src.xxx import ...`（绝对导入）。模块内可保留基底现有的 `try/except ImportError` 双写法以兼容内核单测，但**新增代码一律用 `from src.xxx`**。
2. **内核边界（design D6）**：以下能力视为「内核」，**必须**从 `from src.core.kernel import` 取，MUST NOT 直接 import 内核各子包内部：
   - `SimpleProcessor`（字幕→笔记 + 思维导图）、`SemanticAligner`/`AlignedSegment`、`ContentFilter`/`FilterResult`、`MarkdownGenerator`/`MarkdownOutput`
   - `TaskQueue`/`get_task_queue`、`TaskWorker`/`get_task_worker`/`start_worker`/`stop_worker`
   - `BaseLLM`/`LLMFactory`（8 家 OpenAI 兼容适配）
   - `SRTParser`/`SubtitleItem`、`PDFParser`/`PDFPage`/`Chapter`
   - `Database`/`TaskRepository`
   - `logger`/`TaskLogger`
   - 内核还含：`prompts/`（restructure/generate_directly/generate_with_pdf_reference/classify/mindmap/mindmap_outline/pdf_structure_analysis）、`utils/security.py` + `core/security_constants.py`（注入防护）、`utils/srt_validator.py`、思维导图导出。
   - 内核**只做适配性微调**（如 `task_repository.py` 扩列、`pdf_parser.py` 套 `PdfReferenceProvider`），不得重写其内部实现。
3. **语言约定**：全部注释、docstring、用户可见错误信息、日志为**中文**；枚举值/字段名/协议字面量/规范术语（pending/running/…、permanent/7d/30d、xmind/png/md 等）保留英文。
4. **路径约定**：所有产物路径在 SQLite 中**存相对 `DATA_ROOT` 的 POSIX 相对路径**（如 `videos/task_abc/clip.mp4`），使用处由 `Path(DATA_ROOT) / rel` 解析为绝对路径。MUST NOT 把宿主绝对路径落库。
5. **状态变更顺序（design D10，关键）**：每次节点/任务状态变化 MUST **先写 SQLite（`task_repository`），再向 SSE EventBus 推事件**。SSE 是瞬态、SQLite 是权威态。
6. **取消协议**：DAG 向每个运行节点注入 `CancelToken`；节点 MUST 周期性调用 `ctx.cancel.is_cancelled()`，被取消时尽快抛 `CancelledError`，**丢弃**本节点半成品，**保留**已 completed 节点产物。
7. **临时文件隔离（design D9）**：一切中间文件（下载分片、音频切片、ASR 中间结果、截图临时帧）MUST 写 `data/temp/<task_id>/`，MUST NOT 写入五类产物目录。
8. **并发（design D8）**：复用 `TaskQueue(max_concurrent)`，默认 **1**，设置页 1~3 可配，越界拒绝并回落。跨任务并发与单任务内 VAD 分段并行共享同一 CPU/IO 预算上限。
9. **启动恢复（design D10 / spec task-pipeline）**：进程启动时扫库，把残留 `running` 任务标 `failed`，error 注明「重启中断于 `<节点名>` 节点」；并触发一次 retention 清理扫描（spec storage-retention）。
10. **测试命令**：`cd /Volumes/worknie/Desktop/ai_code/vid2note/backend && .venv/bin/python -m pytest`。

---

## 1. Task 模型字段契约（`src/models/task.py`）

> 基底现有 `Task` dataclass 与 `tasks` 表面向「上传 SRT/TXT/PDF」线性流程，v1 改为「六步 DAG + 视频/音频/链接来源」。下表是**新的规范字段集**；旧字段处置见本节末尾。

### 1.1 字段清单（字段名 + 类型 + 用途）

| 字段名 | Python 类型 | SQLite 列类型 | 用途 |
|---|---|---|---|
| `id` | `str` (PK) | `TEXT PRIMARY KEY` | 任务 ID，格式 `task_<12hex>`（沿用 `upload.generate_task_id`） |
| `source_type` | `str` (Enum) | `TEXT NOT NULL` | 媒体来源：`youtube` / `bilibili` / `direct` / `local_video` / `local_audio` |
| `source_url` | `Optional[str]` | `TEXT` | 在线来源原始链接；`local_*` 来源为 None |
| `title` | `Optional[str]` | `TEXT` | 任务标题（默认取视频标题/上传文件名），历史页与思维导图根节点复用 |
| `status` | `str` (Enum) | `TEXT NOT NULL DEFAULT 'pending'` | 总体状态：`pending` / `running` / `completed` / `failed` / `cancelled` |
| `progress` | `int` (0–100) | `INTEGER DEFAULT 0` | 总体进度百分比（= 六节点进度的加权聚合，由 DAG 计算） |
| `video_path` | `Optional[str]` | `TEXT` | 视频产物**相对路径**（download 节点产出 / local_video 上传落盘） |
| `audio_path` | `Optional[str]` | `TEXT` | 音频产物相对路径（extract_audio 产出 / local_audio 上传落盘） |
| `srt_path` | `Optional[str]` | `TEXT` | SRT 字幕产物相对路径（asr 节点产出） |
| `note_path` | `Optional[str]` | `TEXT` | Markdown 笔记产物相对路径（note 节点产出） |
| `pdf_path` | `Optional[str]` | `TEXT` | 用户附带的 PDF 讲义路径（**输入**，非流水线产物；一一配对） |
| `mindmap_paths` | `list[str]` | `TEXT` (JSON) | 思维导图产物相对路径列表，如 `["notes/<tid>/a.xmind","...png"]` |
| `screenshot_paths` | `list[str]` | `TEXT` (JSON) | 截图产物相对路径列表（仅 `extract_images=True` 时） |
| `node_statuses` | `dict` | `TEXT` (JSON) | 六节点各自状态机（结构见 1.2），权威节点视图 |
| `llm_provider` | `Optional[str]` | `TEXT` | LLM 引擎：`qwen`/`glm`/`deepseek`/`moonshot`/`baidu`/`doubao`/`minimax`/`ollama` |
| `llm_model` | `Optional[str]` | `TEXT` | LLM 模型名（默认 `deepseek-v4-flash`） |
| `asr_engine` | `Optional[str]` | `TEXT` | 任务选定的 ASR 引擎：`asrtools` / `whisper_cpp` / `external`（+ 策略 online_first/single 存 settings） |
| `pdf_mode` | `str` (Enum) | `TEXT DEFAULT 'pypdf'` | PDF 方案：`pypdf` / `mineru`（默认 pypdf，切换仅对新任务生效） |
| `extract_images` | `bool` | `BOOLEAN DEFAULT 0` | 截图嵌入开关（**默认 False**） |
| `output_language` | `str` (Enum) | `TEXT DEFAULT 'zh'` | 笔记输出语言：`zh` / `en`（默认 zh） |
| `mindmap_formats` | `list[str]` | `TEXT` (JSON) | 思维导图导出格式子集，取值 `["xmind","png","md"]` 子集（默认 `["xmind"]`） |
| `queue_position` | `Optional[int]` | `INTEGER` | 排队等待位次（pending 任务在队列中的 FIFO 位次，1 为队首；running/终态为 None） |
| `error` | `Optional[str]` | `TEXT` | 总体/失败节点中文错误信息（含失败节点名 + 归类原因） |
| `created_at` | `datetime` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 创建时间（提交入队） |
| `updated_at` | `datetime` | `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | 最近状态变更时间（每次 `repo.update` 自动刷新） |
| `finished_at` | `Optional[datetime]` | `TIMESTAMP` | 进入终态（completed/failed/cancelled）时间 |

> **JSON 列读写约定**：`mindmap_paths`/`screenshot_paths`/`node_statuses`/`mindmap_formats` 在 Python 侧为 dict/list，落库前 `json.dumps`，读出 `json.loads`，空值分别存 `[]` / `{}` / `[]`（MUST NOT 存 NULL，便于前端直接消费）。`from_db_row` 与 `to_dict` MUST 处理 JSON 解包与 datetime 解析（沿用基底现有安全解析风格）。

### 1.2 `node_statuses` 结构（六节点权威视图）

```jsonc
{
  "download":      {"status":"completed","progress":100,"started_at":"2026-07-25T10:00:00","finished_at":"2026-07-25T10:02:30","error":null,"product":{"path":"videos/task_abc/clip.mp4","size_bytes":123456789}},
  "extract_audio": {"status":"skipped",  "progress":0,  "started_at":null,                 "finished_at":null,                "error":null,"product":null},
  "asr":           {"status":"running",  "progress":42, "started_at":"2026-07-25T10:02:31","finished_at":null,                "error":null,"product":null},
  "note":          {"status":"pending",  "progress":0,  "started_at":null,                 "finished_at":null,                "error":null,"product":null},
  "mindmap":       {"status":"pending",  "progress":0,  "started_at":null,                 "finished_at":null,                "error":null,"product":null},
  "cleanup":       {"status":"pending",  "progress":0,  "started_at":null,                 "finished_at":null,                "error":null,"product":null}
}
```

- **节点名固定六枚**：`download` / `extract_audio` / `asr` / `note` / `mindmap` / `cleanup`（顺序即 DAG 拓扑序，MUST NOT 改变）。
- **节点 `status` 枚举**：`pending` / `running` / `completed` / `failed` / `skipped`（与 spec task-pipeline 一致）。
- **节点 `progress`**：0–100，独立于总体 `progress`。
- **`product`**：该节点产出的产物登记（`path` 相对 `DATA_ROOT` + `size_bytes`）；cleanup 节点恒为 `null`；skipped 节点 `null`（local_audio 的 audio_path 由上传文件直接登记到顶层 `audio_path`，extract_audio 节点 product 仍为 null）。
- 顶层 `video_path`/`audio_path`/`srt_path`/`note_path` 是**便捷指针**，DAG MUST 保持其与 `node_statuses[<产出节点>].product.path` 一致（节点完成时同步写两处）。

### 1.3 总体 `status` 合法迁移（spec task-pipeline）

```
pending → running → completed
                 → failed
pending → cancelled
running → cancelled
running → failed          # 节点失败 / 重启恢复
failed  → running         # 仅经节点级 rerun 触发（合法）
cancelled → running       # 仅经节点级 rerun 触发（合法）
```
- 其余迁移（如 `completed→running` 未经 rerun、`failed→completed` 未经 rerun）MUST 拒绝并记录一次非法迁移尝试。
- 终态（completed/failed/cancelled）任务 MUST NOT 再被调度执行（`reserve_pending_task` 只取 pending）。

### 1.4 旧字段处置（基底 → v1）

基底 `Task`/`tasks` 表的旧字段在 v1 **不再使用**，但因 SQLite `ALTER` 列删除受限、且工作区已清空（commit `23e4f8c`），**新库直接用新 schema**；对存量库迁移采用「幂等 ADD COLUMN，旧列留存不读」策略：

| 基底旧字段 | v1 处置 |
|---|---|
| `current_step` / `message` | **废弃**，由 `node_statuses`（当前 running 节点 + 进度）替代 |
| `download_url` / `mindmap_url` | **废弃**，下载由 `/api/v1/tasks/{id}/products/{kind}` 派生，不入库 |
| `srt_file` / `txt_file` / `pdf_file` / `output_file` / `mindmap_file` | 分别由 `srt_path` / （删除 txt，v1 无 txt 输入）/ `pdf_path`（输入）/ `note_path` / `mindmap_paths` 替代 |
| `srt_original_name` / `txt_original_name` / `pdf_original_name` | **合并到** `title` |
| `export_mindmap` / `mindmap_format` | **合并到** `mindmap_formats`（默认 `["xmind"]`；空表 `[]` 表示不导出） |
| `error_message` | 由 `error` 替代 |

> `models/task.py`、`db/task_repository.py`、`core/worker.py` 中对旧字段的引用属于「改造/重写」范围（见 design D6 表），由对应 Implement 任务统一替换；新代码 MUST NOT 再引用旧字段名。

---

## 2. 产物目录契约（design D9 / spec storage-retention）

### 2.1 根与子目录

所有产物与 SQLite 落于单一持久化 Docker volume，根目录由环境变量 `DATA_ROOT` 指定（默认 `backend/data`，容器内约定 `/app/data`）：

```
$DATA_ROOT/
├── tasks.db                     # SQLite（WAL，见 §3）
├── videos/<task_id>/*.mp4       # 视频产物（download / local_video）
├── audio/<task_id>/*.wav        # 音频产物（extract_audio / local_audio），16kHz 单声道
├── srt/<task_id>/*.srt          # SRT 字幕产物（asr）
├── notes/<task_id>/*.md         # Markdown 笔记产物（note）
│                /*.xmind|png|md # 思维导图产物（mindmap，与笔记同目录便于相对引用）
├── screenshots/<task_id>/*.png  # 截图产物（note 节点，extract_images=True）
└── temp/<task_id>/              # 任务级隔离临时文件（下载分片/音频切片/ASR 中间/截图帧）
```

### 2.2 目录约定（必守）

1. **按类型分目录**：任一类产物 MUST NOT 出现在另一类目录中（spec storage-retention）。
2. **按 `task_id` 二级隔离**：每类目录下按 `task_id` 建子目录，便于按任务定位/统计/清理与节点级 rerun 清场。
3. **临时隔离**：`temp/<task_id>/` 是唯一临时区；cleanup 节点必清本任务 temp。
4. **思维导图与笔记同放 `notes/<task_id>/`**：思维导图是笔记的派生产物，同目录便于 Markdown 内图片用相对路径引用（design D4 Open Question 倾向相对路径），也避免新增第六类目录。
5. **文件名安全**：所有落盘文件名经 `kernel.utils.security.secure_filename` 处理（防路径遍历），保留原始扩展名。
6. **目录创建**：各节点在产出前 `mkdir(parents=True, exist_ok=True)` 创建自己的产物子目录；MUST NOT 预创全部目录。

### 2.3 环境变量

| 变量 | 默认 | 用途 |
|---|---|---|
| `DATA_ROOT` | `backend/data` | 产物 + SQLite 根（持久化 volume 挂载点） |
| `DB_PATH` | `$DATA_ROOT/tasks.db` | SQLite 路径（沿用基底 `Database` 的 `DB_PATH` 支持） |
| `MAX_CONCURRENT` | `1` | 跨任务最大并发（设置页可覆盖；1~3） |

> 基底的 `OUTPUT_DIR` / `server.temp_dir`（上传目录）**废弃**，统一收敛到 `DATA_ROOT`。

---

## 3. SQLite 变更契约（design D9 / spec storage-retention）

### 3.1 `tasks` 表新 schema（`src/db/database.py::_init_db`）

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id               TEXT PRIMARY KEY,
    source_type      TEXT NOT NULL,
    source_url       TEXT,
    title            TEXT,
    status           TEXT NOT NULL DEFAULT 'pending',
    progress         INTEGER DEFAULT 0,
    video_path       TEXT,
    audio_path       TEXT,
    srt_path         TEXT,
    note_path        TEXT,
    pdf_path         TEXT,
    mindmap_paths    TEXT DEFAULT '[]',      -- JSON 数组
    screenshot_paths TEXT DEFAULT '[]',      -- JSON 数组
    node_statuses    TEXT DEFAULT '{}',      -- JSON 对象（六节点）
    llm_provider     TEXT,
    llm_model        TEXT,
    asr_engine       TEXT,
    pdf_mode         TEXT DEFAULT 'pypdf',
    extract_images   BOOLEAN DEFAULT 0,
    output_language  TEXT DEFAULT 'zh',
    mindmap_formats  TEXT DEFAULT '["xmind"]', -- JSON 数组
    queue_position   INTEGER,
    error            TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at      TIMESTAMP
);
-- 索引（沿用基底 + 新增 source_type 便于历史筛选）
CREATE INDEX IF NOT EXISTS idx_status       ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_created_at   ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_source_type  ON tasks(source_type);
```

### 3.2 新增 `settings` 表（key/value，spec storage-retention「配置落 SQLite」）

```sql
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,                -- 标量存字面量；复杂值存 JSON
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**约定 key 命名空间**（全部持久化、跨重启保留、设置页读写）：

| key | value 示例 | 用途 |
|---|---|---|
| `llm.provider` | `"deepseek"` | 默认 LLM 引擎（默认 DeepSeek） |
| `llm.model` | `"deepseek-v4-flash"` | 默认 LLM 模型 |
| `llm.credentials` | JSON `{...}` | 8 家凭证（api_key/base_url/model 等，按 provider 聚合） |
| `asr.engine` | `"asrtools"` | 默认 ASR 引擎 |
| `asr.strategy` | `"online_first"` | `online_first` / `single` |
| `asr.config` | JSON `{endpoint,...}` | AsrTools 凭证 / whisper.cpp 模型路径 / external endpoint |
| `pdf.mode` | `"pypdf"` | `pypdf` / `mineru` |
| `pdf.mineru_endpoint` | `""` | 外部 MinerU endpoint（空=本地 CPU） |
| `bilibili.cookie` | JSON `{SESSDATA,bili_jct,DedeUserID}` | Bilibili 登录态（仅 bilibili 来源用） |
| `concurrency.max` | `"1"` | 跨任务最大并发（1~3） |
| `note.output_language` | `"zh"` | 笔记输出语言 |
| `note.extract_images` | `"false"` | 截图嵌入开关 |
| `note.image_quality` | `"medium"` | low/medium/high |
| `retention.video` / `.audio` / `.srt` / `.note` / `.screenshot` | `"7d"`/`"30d"`/`"permanent"` | 五类产物各自保留策略 |
| `advanced.chunk_size` / `.temperature` / `.max_retries` | `"4000"`/`"0.3"`/`"3"` | 高级参数 |

> 首次启动（settings 表为空）MUST 写入合法默认值（spec storage-retention）：LLM=DeepSeek `deepseek-v4-flash`、并发 1、PDF pypdf、五类保留默认（建议 video/audio=7d、srt/screenshot=30d、note=permanent）、语言 zh、截图关。非法取值 MUST 拒绝且不改原值。

### 3.3 启用 WAL（design Risks、tasks 1.4）

在 `Database._get_connection()` 建连后执行：

```python
conn.execute("PRAGMA journal_mode=WAL")     # 提高并发写容忍
conn.execute("PRAGMA synchronous=NORMAL")   # WAL 下安全且更快
conn.execute("PRAGMA foreign_keys=ON")
conn.row_factory = sqlite3.Row
```

> 写路径 MUST 集中在 `task_repository.py`（与 settings 读写一并放此处或新建 `settings_repository.py`，二选一，**不可散落到各模块**）。

### 3.4 迁移方式（基底 schema 在哪、怎么加字段）

- **基底 schema 位置**：`src/db/database.py::_init_db`（CREATE）+ `_migrate_db`（幂等 ALTER）。
- **改造做法**：
  1. **重写 `_init_db` 的 `CREATE TABLE tasks`** 为 §3.1 的新 schema（工作区已清空，新库直接建新表）。
  2. **重写 `_migrate_db`**：保留「`PRAGMA table_info(tasks)` 读列名 → 缺失则 `ALTER TABLE ADD COLUMN`」的幂等模式，逐列补齐 §3.1 新列（含默认值）；新增 `CREATE TABLE IF NOT EXISTS settings`；对已存在的旧库把旧字段数据迁移到新字段（如 `error_message→error`、`output_file→note_path`）后再不复用旧列。MUST NOT 假设列顺序，`from_db_row` 一律按列名读（基底已有此风格，保留）。
  3. **`task_repository.py`**：`create()` 的列清单与 `INSERT` 占位符改为 §3.1 新列；新增 `get_setting(key)/set_setting(key,value)/get_all_settings()`（或新建 `SettingsRepository`）；新增 `list_history(filters, page, page_size)`（状态/来源/关键词筛选 + 分页 + 总数，spec task-pipeline「历史」）、`queue_position_of(task_id)`、`reset_running_on_startup()`（启动恢复）。
  4. **`Task.from_db_row` / `to_dict` / `from_dict`**：同步 §1.1 新字段，含 JSON 解包与 datetime 解析。

---

## 4. 路由契约（`src/api/`）

### 4.1 新增路由清单（prefix `/api/v1`，全部对前端）

| 方法 | 路径 | 用途 | 关键约束 |
|---|---|---|---|
| `POST` | `/api/v1/tasks` | 创建任务 | 接受 `source_url`（多部分或 JSON）**或** 本地音视频文件（`multipart/form-data`）+ 引擎选项（`asr_engine`/`llm_provider`/`llm_model`/`pdf_mode`/`extract_images`/`output_language`/`mindmap_formats`）+ 可选 PDF；调用 `media_ingest.identify_source` 识别 `source_type`；队列满→429；无法识别→400 中文错误 |
| `GET` | `/api/v1/tasks/{task_id}` | 任务详情 | 返回完整 `Task`（含 `node_statuses`/产物路径/`queue_position`） |
| `GET` | `/api/v1/tasks/{task_id}/stream` | SSE 实时进度/日志 | 见 §5.6 / §6.6；`text/event-stream` |
| `POST` | `/api/v1/tasks/{task_id}/rerun?from=<node>` | 节点级重跑 | `from` 取六节点之一；复用上游 completed 产物、缺失回退到缺失节点；校验状态可重跑（failed/cancelled/completed 允许；pending/running 拒绝） |
| `POST` | `/api/v1/tasks/{task_id}/cancel` | 取消任务 | pending→cancelled 移出队列；running→发取消信号；终态→409/提示无效 |
| `GET` | `/api/v1/tasks` | 历史列表 | 筛选 `status`/`source_type`/`q`（关键词，匹配 title/source_url/source_type，大小写不敏感，可组合取交集）+ 分页 `page`/`page_size`，响应含 `total` |
| `POST` | `/api/v1/tasks/batch` | 批量导出 / 重跑 | body `{"action":"export"|"rerun","task_ids":[...]}`；export→把选中 completed 任务的 `note_path` 打包 zip（内按 task 区分）返回下载；rerun→为每个选中任务创建**复用其输入与配置**的新任务入队，原记录不变 |
| `GET` | `/api/v1/tasks/{task_id}/products/{kind}` | 下载产物 | `kind` ∈ `note`/`srt`/`video`/`audio`/`mindmap`/`screenshot`；校验 `is_safe_path(DATA_ROOT, ...)` 后 FileResponse |
| `GET` | `/api/v1/settings` | 读取全部设置 | 返回 §3.2 全部 key（凭证字段脱敏） |
| `PUT` | `/api/v1/settings` | 更新设置 | body 为 key→value 子集；逐项校验（并发 1~3、保留策略枚举、pdf_mode 枚举…），非法拒并返回中文错误；立即持久化并对下一次清理生效；**仅对新任务生效**（不改历史任务） |
| `GET` | `/api/v1/storage/stats` | 存储用量统计 | 返回 `retention.storage_stats()`：`total_bytes` + `by_kind`（五类）+ `top_tasks` |
| `GET` | `/api/v1/health` | 健康检查 | 返 2xx；含 `yt-dlp`/`ffmpeg`/whisper.cpp 可执行性 + 引擎配置态（供前端引擎状态卡） |

### 4.2 旧路由处置（`src/api/` 改造）

| 基底旧路由 | v1 处置 |
|---|---|
| `POST /api/v1/upload/{srt,pdf,txt,task}` | **删除**，合并进 `POST /api/v1/tasks`（multipart：`source_url` 或 `file`，可选 `pdf`） |
| `POST /api/v1/process/start`、`GET /api/v1/process/status/{id}`、`GET /api/v1/process/{id}/download[/mindmap]` | **删除**，由 `POST /api/v1/tasks`（创建即入队）、`GET /api/v1/tasks/{id}`、`GET /api/v1/tasks/{id}/products/{kind}` 替代 |
| `GET/POST/DELETE /api/v1/queue/*`、`/api/v1/queue/stats` | **删除**，统计折叠进 `GET /api/v1/storage/stats` + 任务详情的 `queue_position` |
| `GET /api/v1/config/*`（`api/config.py`） | **改造**为 `GET/PUT /api/v1/settings`（数据源从 config 文件改为 SQLite `settings` 表；基底 `config_manager` 可作为内核只读默认值来源，但权威态在 SQLite） |
| `GET /api/v1/logs/*`（`api/logs.py`） | 保留只读日志查看（任务级日志文件），或折叠进 SSE `log` 事件；Implement 时定 |

> `src/api/__init__.py` 的 `api_router` 注册表相应更新；`main.py` 单容器化后移除 `CORSMiddleware`（design D1）。

---

## 5. Pipeline 六步 DAG 编排契约（`src/pipeline/dag.py`）（design D8 / spec task-pipeline）

### 5.1 拓扑与数据流（每步：输入产物 → 输出产物 → 调用模块）

| # | 节点 | 输入 | 输出产物 | 调用模块（接口见 §6） | 跳过规则 |
|---|---|---|---|---|---|
| 1 | `download` | `source_url` + `source_type` +（bilibili）cookie | `video_path`（videos/） | `media_ingest.download_video` | `source_type ∈ {local_video, local_audio}` → **skipped**（local_video 直接把上传文件登记为 `video_path`） |
| 2 | `extract_audio` | `video_path` | `audio_path`（audio/，16kHz mono WAV） | `media_ingest.extract_audio` | `source_type == local_audio` → **skipped**（上传文件直接登记为 `audio_path`） |
| 3 | `asr` | `audio_path` | `srt_path`（srt/） | `speech_to_text.transcribe` | 无（必执行） |
| 4 | `note` | `srt_path`（+ 可选 `pdf_path` + `pdf_mode`） | `note_path`（notes/）；`extract_images=True` 时另出 `screenshot_paths` | `note_generation.generate`（复用 kernel `SimpleProcessor` + `screenshot.embed_screenshots`） | 无 |
| 5 | `mindmap` | `note_path` | `mindmap_paths`（notes/） | `mindmap.generate`（复用 kernel 导出） | `mindmap_formats == []` → skipped；否则必执行 |
| 6 | `cleanup` | 全部产物 + `node_statuses` | 无产物 | `retention.cleanup_task_temp` + 触发 `retention.run_cleanup_scan` | **永不跳过**（try/finally 必执行，成功与失败两条路径都跑） |

### 5.2 节点通用契约

1. **产物登记**：非 cleanup 节点完成时 MUST 调 `ctx.register_product(kind, rel_path, size_bytes)`，同步写顶层对应 `*_path`（或 `mindmap_paths`/`screenshot_paths`）与 `node_statuses[<node>].product`。
2. **缺上游产物即终止**：节点开始前若必需上游产物在 `node_statuses` 中不存在或文件已丢失，MUST 立即失败，error = `"缺少上游产物：<节点名>"`，MUST NOT 用空输入继续（spec task-pipeline）。
3. **状态先落库再推**：每节点 `pending→running`（写 `started_at`）、进度推进、`→completed`（写 `finished_at`+product）、`→failed`（写 error）均先 `repo.update` 再 `bus.publish`（§0 第 5 条）。
4. **取消检查**：节点执行体周期性 `ctx.cancel.is_cancelled()`，被取消抛 `CancelledError`，DAG 捕获后把当前节点置 failed/cancelled、丢弃半成品、保留已 completed 产物、仍执行 cleanup。
5. **进度回调**：节点经 `ctx.emit_progress(percent, message)` 与 `ctx.emit_log(level, line)` 推送（驱动 SSE `node-progress`/`log`）。

### 5.3 节点级重跑（spec task-pipeline / design D8）

- `POST /api/v1/tasks/{id}/rerun?from=<node>` → `DagRunner.run(from_node=<node>)`：
  1. **校验上游**：`from_node` 之前所有非 skipped 节点须 `completed` 且产物文件存在且完整；任一缺失 → **回退**到最早的缺失节点起重跑，error/日志说明回退原因。
  2. **干净工作上下文**：先清空 `data/temp/<task_id>/` 与 `from_node` 及其下游节点的旧产物（含顶层 `*_path` 与 `node_statuses[*].product`），**MUST NOT 复用失败节点的半成品**。
  3. **复用上游**：`from_node` 之前的 completed 节点**不重跑**，其产物直接作为下游输入。
  4. **级联重算**：从 `from_node` 起按拓扑序重新执行至 cleanup。
  5. **清除失败记录**：重跑全部成功后，`status→completed`，原 `error` 与失败节点 error 归档清除。
- 合法性：`from_node` 必须是六节点之一；任务须处于 failed/cancelled/completed（pending/running 拒绝 409）。

### 5.4 任务总体状态推进（DAG 负责）

- 入队：`status=pending`，六节点 `pending`（被跳过节点在 worker 取起时置 `skipped`）。
- worker 取起（`reserve_pending_task`）：`status=running`，首个非 skipped 节点 `running`。
- 全部非 skipped 节点（含 cleanup）completed → `status=completed`，`progress=100`，`finished_at=now`。
- 任一非 skipped 节点 failed → `status=failed`，记录失败节点名 + 中文 error，**仍执行 cleanup**。
- 取消：`status=cancelled`，丢弃中断节点半成品，保留已 completed 产物。
- `progress`（总体）= 六节点进度的加权平均（cleanup 权重较小；skipped 节点按 100 计）。

### 5.5 来源识别驱动的跳过（spec media-ingest）

| source_type | download | extract_audio | asr | note | mindmap | cleanup |
|---|---|---|---|---|---|---|
| `youtube` / `bilibili` / `direct` | 执行 | 执行 | 执行 | 执行 | 执行 | 执行 |
| `local_video` | **skipped**（上传文件=video_path） | 执行 | 执行 | 执行 | 执行 | 执行 |
| `local_audio` | **skipped** | **skipped**（上传文件=audio_path） | 执行 | 执行 | 执行 | 执行 |

> `identify_source` 无法识别（纯文本、不支持协议、既非已知平台链接又无本地文件）→ 创建任务即 400 `"无法识别的媒体来源"`，不入队。

### 5.6 与基底的衔接（内核复用点）

- DAG 不重写「字幕→笔记」逻辑，note 节点调 kernel `SimpleProcessor.process(subtitle_file=srt_path, pdf_file=pdf_path or None)`，返回 Markdown 字符串 → 清洗（剥 ```` ```markdown ```` / ```` ``` ```` 包裹）→ 落盘 `notes/<tid>/<safe>.md`。
- mindmap 节点调 kernel `SimpleProcessor.generate_mindmap(markdown_content, output_path, format=...)`，按 `mindmap_formats` 多次产出。
- worker（`core/worker.py`）改造：`_execute_processing` 的线性逻辑替换为 `DagRunner(task_id).run()`；并发控制沿用 `TaskQueue.max_concurrent` 与 `reserve_pending_task`。

---

## 6. 模块接口契约（后续 Implement agent 严格遵守函数签名）

> 通用回调类型（由 DAG 的 `NodeContext` 提供，桥接 repo + EventBus）：
> - `ctx.emit_progress(percent: int, message: str | None = None) -> None`：先落库 `node_statuses[node].progress` 再推 `node-progress`。
> - `ctx.emit_log(level: str, line: str) -> None`：推 `log` 事件（level ∈ info/ok/warn/error）。
> - `ctx.cancel.is_cancelled() -> bool`：取消信号。
> - `ctx.product_path(kind: str, ext: str) -> Path`：返回 `<DATA_ROOT>/<kind>s/<task_id>/<safe_base>.<ext>` 绝对路径并确保父目录存在。
> - `ctx.register_product(kind: str, rel_path: str, size_bytes: int) -> None`：登记产物（写顶层字段 + node_statuses）。
> - `ctx.task`：当前 `Task` 快照；`ctx.settings`：`SettingsSnapshot`（从 SQLite settings 读出的强类型快照）。

### 6.1 `media_ingest/`（design D6 新增 / spec media-ingest）

```python
# src/media_ingest/__init__.py
class SourceType(str, Enum):
    YOUTUBE = "youtube"; BILIBILI = "bilibili"; DIRECT = "direct"
    LOCAL_VIDEO = "local_video"; LOCAL_AUDIO = "local_audio"

@dataclass
class UploadedFile:
    abs_path: str; original_name: str; mime: str; size_bytes: int

def identify_source(source_url: str | None, uploaded: UploadedFile | None) -> SourceType:
    """识别五类来源；无法识别 raise ValueError('无法识别的媒体来源')。"""

def download_video(ctx, source_url: str, source_type: SourceType,
                   cookies: dict | None) -> str:
    """yt-dlp 整段最高画质下载到 ctx.product_path('video', ext)；需合并独立音视频流时自动合并。
    仅 source_type ∈ {youtube,bilibili,direct} 可调；本地来源调用方应跳过本节点。
    Bilibili 注入 cookies；其它来源 MUST NOT 附 bilibili cookie。
    仅在产物可读、时长>0 时返回相对路径并 ctx.register_product。
    失败 raise DownloadError(kind, message_zh)，
        kind ∈ {invalid_url, needs_login, network, risk_control, tool_missing}。"""

def extract_audio(ctx, video_rel_path: str) -> str:
    """ffmpeg 从视频提取 16kHz 单声道 WAV 到 ctx.product_path('audio','wav')；
    时长与源一致（容差内）；无音轨/ffmpeg 非零退出 raise ExtractError(message_zh, ffmpeg_summary)。"""
```

### 6.2 `speech_to_text/`（design D2/D3 / spec speech-to-text）

```python
# src/speech_to_text/__init__.py
@dataclass
class Cue:
    start: float   # 秒
    end: float     # 秒
    text: str

class AsrEngine(ABC):
    name: str
    @abstractmethod
    def transcribe(self, audio_path: str, ctx) -> list[Cue]: ...

class AsrToolsEngine(AsrEngine): ...      # 在线（剪映/必剪），默认首选
class WhisperCppEngine(AsrEngine): ...    # 本地 CPU + int8，MUST NOT 发网络请求
class ExternalAsrEngine(AsrEngine): ...   # HTTP endpoint，地址来自配置

def transcribe(ctx, audio_rel_path: str, srt_out_rel_path: str,
               asr_config: AsrConfig) -> str:
    """按策略（online_first 默认 / single）选引擎；
    音频 > 阈值（初定 5 分钟）按 VAD 静音切分、各段并行调引擎（并发受队列预算约束）、
    段内时间戳叠加段起始偏移拼回 → cues_to_srt 写单调递增、覆盖完整时长的 SRT；
    在线降级写结构化日志（原因/原引擎/目标引擎/时间戳）；全不可用 raise AsrError。
    返回 srt 相对路径并 ctx.register_product('srt', ...)。"""

def cues_to_srt(cues: list[Cue]) -> str:
    """Cue 列表 → 标准 SRT 文本（HH:MM:SS,mmm --> HH:MM:SS,mmm）。"""

# 字幕一律 ASR：MUST NOT 存在抓取平台官方字幕(CC)的代码路径。
```

### 6.3 `screenshot/`（design D4 / spec note-generation 截图嵌入）

```python
# src/screenshot/__init__.py
def parse_img_marks(markdown_text: str) -> list[int]:
    """正则扫描 LLM 输出的 [IMG:<秒>] 标记，返回合法秒数列表。"""

def capture_frame(video_abs_path: str, ts_seconds: int, out_abs_path: str) -> bool:
    """ffmpeg -ss <ts> -i <video> -frames:v 1 截帧；成功 True，失败 False。"""

def embed_screenshots(ctx, markdown_text: str, srt_rel_path: str,
                      video_rel_path: str | None) -> tuple[str, list[str]]:
    """extract_images=True 时由 note 节点调用：解析 [IMG:<秒>]，
    逐个 ffmpeg 截帧到 screenshots/<tid>/，替换为 Markdown 图片语法（相对路径）；
    越界/无效秒/截帧失败 → 静默跳过且笔记不残留原始标记；单标记失败不中断。
    返回 (清洗后 markdown, 截图相对路径列表)。"""
```

### 6.4 `note_generation/`（design D6 复用 / spec note-generation）

```python
# src/note_generation/__init__.py
@dataclass
class NoteOptions:
    extract_images: bool
    output_language: str   # zh / en
    pdf_mode: str          # pypdf / mineru

def generate(ctx, srt_rel_path: str, pdf_rel_path: str | None,
             llm, options: NoteOptions) -> str:
    """MUST:
    1. 校验 srt 存在；kernel.SRTValidator 喂 LLM 前校验（时间戳格式/结束>开始/非空/不超上限），非法 raise。
    2. kernel 注入防护（中和注入模式 + 转义尖括号 + 剥控制字符 + 长度截断）。
    3. 纯文本喂入（剥序号/时间戳行/HTML 标签）；extract_images=True 时带时间戳喂入。
    4. 无 PDF → kernel SimpleProcessor.process(srt, None)（generate_directly 分支）；
       有 PDF → pdf_reference 解析后走 generate_with_pdf_reference 分支（复用 kernel 模板）。
    5. 清洗 LLM 输出（剥 ```markdown / ``` 包裹）。
    6. extract_images=True → screenshot.embed_screenshots(...)。
    7. 落盘 notes/<tid>/<safe>.md，ctx.register_product('note', ...)，返回相对路径。"""
```

### 6.5 `mindmap/`（spec mindmap-export；复用 kernel `SimpleProcessor.generate_mindmap`）

```python
# src/mindmap/__init__.py
def generate(ctx, note_rel_path: str, formats: list[str]) -> list[str]:
    """唯一输入来源 = note-generation 最终笔记（非字幕/音频/视频）；
    按 formats（["xmind","png","md"] 子集）各自产出，复用 kernel 导出；
    不支持格式（svg/pdf/mm）raise ValueError('v1 仅支持 xmind/png/md')；
    多格式时单格式失败不拖累其它；落盘 notes/<tid>/，逐个 ctx.register_product；
    返回产物相对路径列表。"""
```

### 6.6 `pipeline/dag.py`（design D8 / spec task-pipeline）

```python
# src/pipeline/dag.py
class NodeName(str, Enum):
    DOWNLOAD = "download"; EXTRACT_AUDIO = "extract_audio"; ASR = "asr"
    NOTE = "note"; MINDMAP = "mindmap"; CLEANUP = "cleanup"

NODE_ORDER: list[NodeName] = [DOWNLOAD, EXTRACT_AUDIO, ASR, NOTE, MINDMAP, CLEANUP]

def skip_nodes_for(source_type: SourceType) -> set[NodeName]:
    """local_video → {DOWNLOAD}；local_audio → {DOWNLOAD, EXTRACT_AUDIO}；其余 → set()。"""

@dataclass
class NodeContext:
    task_id: str; task: Task; node: NodeName
    data_root: Path; work_temp: Path          # data/temp/<task_id>
    repo: TaskRepository; settings: SettingsSnapshot
    bus: "EventBus"; cancel: "CancelToken"
    def product_path(self, kind: str, ext: str) -> Path: ...
    def register_product(self, kind: str, rel_path: str, size_bytes: int) -> None: ...
    def emit_progress(self, percent: int, message: str | None = None) -> None: ...
    def emit_log(self, level: str, line: str) -> None: ...

class DagRunner:
    def __init__(self, task_id: str, repo: TaskRepository, bus: "EventBus",
                 settings: SettingsSnapshot, data_root: Path): ...
    def run(self, from_node: NodeName | None = None) -> None:
        """from_node=None 从首个非 skipped 节点执行；指定则 §5.3 节点级重跑。
        清理节点 try/finally 必执行；状态先 repo 落库再 bus 推。"""
    def request_cancel(self) -> None: ...
```

### 6.7 `retention/`（design D9 / spec storage-retention）

```python
# src/retention/__init__.py
class RetentionPolicy(str, Enum):
    PERMANENT = "permanent"; DAYS_7 = "7d"; DAYS_30 = "30d"

PRODUCT_KINDS = ["video", "audio", "srt", "note", "screenshot"]

@dataclass
class CleanupReport:
    deleted: list[str]; freed_bytes: int; skipped_active: int

def cleanup_task_temp(task_id: str) -> None:
    """清空 data/temp/<task_id>/（cleanup 节点调用）。"""

def run_cleanup_scan(repo: TaskRepository, data_root: Path, settings: SettingsSnapshot,
                     clock: Callable[[], datetime] = datetime.now) -> CleanupReport:
    """周期性 + 启动时调用：按五类各自策略删过期（permanent 永不删）；
    跳过未达终态（pending/running）任务的产物；删后 repo 置空对应产物引用。"""

def storage_stats(data_root: Path) -> dict:
    """返回 {'total_bytes': int, 'by_kind': {kind: int, ...5类},
              'top_tasks': [{'task_id','bytes'}, ...]}，供 GET /api/v1/storage/stats。"""
```

### 6.8 SSE 推送层（`src/sse/` 或 `src/api/tasks.py`）（design D10 / spec task-pipeline）

```python
# src/sse/__init__.py
class EventBus:
    def publish(self, task_id: str, event_type: str, data: dict) -> None:
        """事件类型 ∈ {node-entered, node-progress, log, node-completed, node-failed,
        task-completed, task-failed, task-cancelled, snapshot}；
        每事件自动注入 task_id / node（log 除外）/ ts；非阻塞 fan-out。"""
    def snapshot(self, task_id: str) -> dict:
        """当前总体 status + 六节点最新状态（从 repo 读权威态）。"""
    async def subscribe(self, task_id: str) -> AsyncIterator[dict]:
        """先推一个 snapshot（断线重连重建视图），再续推实时事件；
        任务进入终态 → 推 task-* 后主动关闭连接；
        不存在 / 已终态任务订阅 → 推当前态（或'任务不存在'）并正常关闭，MUST NOT 抛未捕获错误。"""

# 端点（api/tasks.py）
@router.get("/tasks/{task_id}/stream")
async def stream(task_id: str):
    return EventSourceResponse(bus.subscribe(task_id))   # sse-starlette
```

---

## 7. 改造范围速查（design D6 三类，给 Implement agent 分工）

| 类别 | 模块 | 动作 | 关联契约节 |
|---|---|---|---|
| **内核（原样复用 + 微调）** | `llm/`、`prompts/`、`core/simple_processor`、`aligner`、`filter`、`generator`、`parsers/srt_parser`、`utils/security`+`core/security_constants`、`utils/srt_validator`、思维导图导出 | 经 `core/kernel` 导出；不改内部 | §0.2 |
| **内核（微调）** | `db/database.py`、`db/task_repository.py`、`models/task.py` | 新 schema + WAL + settings 表 + 历史/位次/启动恢复方法 | §1、§3 |
| **改造（换头/换实现）** | `api/*`（路由收编为 §4）、`core/worker.py`（线性→调 DagRunner）、`parsers/pdf_parser.py`（套 `PdfReferenceProvider`）、`main.py`（单容器、移除 CORS、启动恢复 + retention 扫描）、`config/manager.py`（默认值来源，权威让位 SQLite settings） | — | §4、§5.6、§0 |
| **新增** | `media_ingest/`、`speech_to_text/`、`screenshot/`、`note_generation/`、`mindmap/`、`pdf_reference/`（pypdf/mineru/external 三 provider）、`pipeline/dag.py`、`retention/`、`sse/` | 严格按 §6 签名 | §6 |

> 任何模块对外暴露的能力，其**函数名、参数名、参数顺序、返回类型、异常类型**以本契约 §6 为准；Implement agent 不得擅自改名或增删必选参数。如确需调整，先改本契约并经批准。
