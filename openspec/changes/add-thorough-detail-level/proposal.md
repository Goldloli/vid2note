## Why

现有「超详细」(exhaustive) 档采用 map-reduce 引擎（fork 自 ai_srt2md，为旧模型上下文受限时代设计），把一份 2.5 万 token 的 2 小时课程字幕通过"切段→证据→蓝图→逐章深写→逐章审校"层层重发，**膨胀成 78.8 万 token 输入**——单任务成本约 ¥0.60、耗时约 35 分钟、34 次串行调用，且对 DeepSeek 自动缓存（best-effort）失效极敏感（实测同代码同配置，命中率可从 57% 掉到 3%，单任务多花约 ¥0.24）。DeepSeek-v4 提供 1M 上下文，使"全文常驻每次调用上下文"成为可能，可从根上消灭重复发送。已用真实字幕实测替代引擎（全文常驻 + 理解→分章深写）：**成本约其 1/7（¥0.087 vs ¥0.598）、速度快约 9 倍（3.8 分钟 vs 35 分钟）、缓存命中率 86% vs 57%，产出字数追平（27078 vs 28565）、结构密度更高（57 vs 55 个 H3）**。本变更新增「比较详细」(thorough) 档承载该引擎，与现有 exhaustive 并存，供用户使用后择优保留。

## What Changes

- 新增第五个笔记详细程度档位 `thorough`（用户可见名"比较详细"），插在 `detailed` 与 `exhaustive` 之间；默认档位不变（仍 `balanced`）。
- 新增 `SimpleProcessor._generate_thorough_with_fullcontext` 引擎（双钴）：**全文常驻上下文**——阶段 1 全局理解（全文 → 6-8 章大纲 JSON + 高置信术语表，1 次调用）→ 阶段 2 分章深写（每章以 `[system, 全文+规划指令, assistant(大纲), 本章深写指令]` 发起，全文与大纲作为跨章稳定前缀命中缓存，M 次调用）→ 机械组装终稿（无 LLM）。
- 后端 5 处写死四档的白名单同步加入 `thorough`（单一事实源 `DETAIL_LEVEL_INSTRUCTIONS` + 设置快照 + 任务创建校验 + 设置写入校验 + E2E 同步脚本）。
- 前端档位选择器（设置页 radiogroup + 创建任务下拉）、中英 i18n 文案加入 `thorough`。
- 用量上报与进度复用现有 `understand`/`draft` 两个 stage/phase（新引擎 `operation_name` 复用"字幕理解"/"章节初稿"中文关键词命中 classifier，runner 免改）。

## Capabilities

### New Capabilities

无。本变更不引入新能力域，全部落在既有 `note-generation` 与 `web-frontend` 之内。

### Modified Capabilities

- `note-generation`：笔记详细程度档位枚举由四档（concise/balanced/detailed/exhaustive）扩展为五档，新增 `thorough` 档及其生成契约——全文常驻理解、6-8 章分章深写、术语前置统一、不捏造；`thorough` 与 `exhaustive` 并存，质量目标相当、成本与耗时显著更低。
- `web-frontend`：设置页档位选择器与创建任务下拉含 `thorough` 选项，中英文案与描述 hint 完整。

## Impact

- **后端**：
  - `backend/src/prompts/detail_level.py`：`DETAIL_LEVEL_INSTRUCTIONS` 增加 `thorough` 条目及指令文本（单一事实源，`normalize_detail_level`/`detail_instruction` 自动放行）。
  - `backend/src/runtime/settings.py`（`_DETAIL_LEVELS`）、`backend/src/runtime/task_service.py`（`_SUPPORTED_NOTE_DETAIL_LEVELS`，API 拒绝点）、`backend/src/api/v1/settings.py`（`_ENUM_ALLOWED["note.detail_level"]`，设置保存点）、`backend/scripts/verify_settings_sync.py`（`DETAIL_VALUES`，E2E 脚本）四处白名单同步。
  - `backend/src/core/simple_processor.py`：`process()` 在 PDF / 无 PDF 两条路径各加 `thorough` 分流；新增 `_generate_thorough_with_fullcontext`（平级于 `_generate_exhaustive_with_understanding`）。
  - `backend/tests/test_note_detail.py`：四档断言更新为五档。
  - `backend/src/runtime/runner.py`：`classify_llm_operation` 与 `_note_stage_progress` **免改**（新引擎复用中文关键词与 phase 名）。
- **前端**：`frontend/src/views/Settings.vue`（`detailLevels` 数组）、`frontend/src/views/Console.vue`（下拉 `<option>`）、`frontend/src/locales/zh.js`、`frontend/src/locales/en.js`；`TaskDetail.vue` 为动态 i18n key 查找，自动适配。
- **复用（不重造）**：`_call_llm`/`_report_usage`、`_sanitize_content`、`_clean_markdown_output`、`SCREENSHOT_INSTRUCTION`、runner.`_embed_screenshots`、`generate_mindmap`、`classify_llm_operation`/`_note_stage_progress`。
- **兼容性**：`thorough` 是新增值，历史任务的 `note_detail_level` 不受影响；默认档位仍 `balanced`；DB schema 不变（`note_detail_level` 为裸 TEXT 列，无 CHECK 约束）；对不支持前缀缓存的 provider 行为与现状一致（只是消息结构变化）。
- **预期效果（以 `llm_usage` 观测验证）**：`thorough` 任务单次成本约 ¥0.09（vs exhaustive ¥0.60）、耗时约 4 分钟（vs 35）、调用约 9 次（vs 34）、缓存命中率 >80%。

## Non-goals

- 不改动现有 `exhaustive` 引擎（与 `thorough` 并存，供用户对比后择优保留或废弃其一）。
- 不改默认档位（仍 `balanced`）。
- 不引入章节级并发调用（双钴 9 次串行已约 4 分钟；并发提速是后续独立 change）。
- 不做 `thorough` ↔ `exhaustive` 历史任务数据迁移。
- 不改 DB schema、不引入 provider 特定显式缓存 API（如 Anthropic `cache_control`）。
- 不改变截图嵌入、PDF 对照、思维导图、保留策略等既有能力的行为。
