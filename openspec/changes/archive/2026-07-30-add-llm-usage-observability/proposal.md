## Why

超详细档位处理长视频会产生 20+ 次 LLM 调用，单次任务输入可达数百万 tokens。当前代码在 adapter 层直接丢弃 `response.usage`（`openai_compatible.py`），用户只能在厂商后台看到日粒度总账，无法回答「这次任务烧了多少 token、哪个阶段烧的、缓存命中多少」。这导致成本不可观测，后续的提示词工程优化（前缀缓存友好化）也无法验证收益。

## What Changes

- 在 OpenAI 兼容 adapter 的 `chat()` 中把 `response.usage` 归一化为普通 dict 暂存到 `llm.last_usage`（DeepSeek 的 `prompt_cache_hit_tokens/prompt_cache_miss_tokens` 与 OpenAI 系的 `prompt_tokens_details.cached_tokens` 统一映射；无缓存字段的 provider 记 0）。
- `SimpleProcessor` 新增可选 `usage_callback` 配置：`_call_llm` 每次调用后读取 `last_usage` 并按 `operation_name` 上报，不改 `chat()` 的返回签名，对不支持 usage 的 mock / 本地模型安全降级。
- runner 的 note / mindmap 两个执行器共享一个任务级聚合器，按「阶段（证据/蓝图/深写/审校/修复/其他）」和「操作名」两级聚合，节点完成后落库到 tasks 表新增的 `llm_usage` JSON 列（照 `note_detail_level` 的 ALTER 迁移范式）。
- 任务详情 API 通过 `Task.to_dict()` 自动透出 `llm_usage`；前端任务详情页新增「LLM 消耗」区块：分阶段表格（调用次数 / 输入 / 缓存命中 / 输出 / 命中率）+ 总计行，无数据时不显示。
- 增加 usage 归一化、聚合、落库、API 透出与前端展示的回归测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `task-pipeline`: 任务新增 `llm_usage` 持久化字段，笔记与思维导图节点执行时必须采集并聚合 LLM 调用用量。
- `note-generation`: 笔记生成的 LLM 调用漏斗必须支持用量上报回调，不改变既有生成行为与返回契约。
- `web-frontend`: 任务详情页必须能展示任务级 LLM 用量，包括缓存命中拆分。

## Impact

- 后端：`OpenAICompatibleLLM.chat`、`SimpleProcessor`（config 回调 + `_call_llm`）、`runner.py` 的 `_note` / `_mindmap` 执行器、Task 模型 / 仓库 / 建表 DDL 增量迁移、相关测试。
- 前端：`TaskDetail.vue` 新展示区块、双语文案、前端测试。
- 运行影响：每次 LLM 调用仅多读一个已返回的字段，无额外网络请求；对无 usage 返回的 provider（如 Ollama 本地）记为 0，不影响任务执行。
- 兼容性：存量任务 `llm_usage` 默认为空对象，前端不显示该区块，无需数据迁移。

## Non-goals

- 不做价格 / 成本估算配置：本变更只观测 token 与缓存命中量，金额由用户按厂商单价自行换算。
- 不持久化每次调用的完整 prompt / 响应内容，只存聚合数值。
- 不做跨任务的全局用量统计页或用量告警。
- 不改动 ai_srt2md 内核的 LLM 适配层返回签名与生成逻辑；usage 采集只挂在调用漏斗上。
- 不在本变更中做提示词工程优化（前缀缓存友好化），那是后续独立变更，本变更是它的度量基础。
