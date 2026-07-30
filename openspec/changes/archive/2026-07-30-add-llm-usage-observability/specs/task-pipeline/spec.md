## ADDED Requirements

### Requirement: 任务级 LLM 用量持久化

系统 MUST 在笔记生成与思维导图节点执行期间采集每一次 LLM 调用的用量（输入 tokens、输出 tokens、缓存命中 tokens、缓存未命中 tokens），并按阶段与操作名两级聚合后持久化到任务的 `llm_usage` 字段。provider 未返回用量或缓存字段时，对应数值 MUST 记为 0 且 MUST NOT 影响任务执行。存量任务无 `llm_usage` 数据时 MUST 默认为空对象，无需迁移历史数据。

#### Scenario: 超详细任务的两级聚合

- **WHEN** 一个超详细任务完成笔记节点（含证据提取、蓝图、逐章深写、逐章审校调用）
- **THEN** 任务 `llm_usage.total` MUST 累计全部调用的 tokens，`llm_usage.by_stage` MUST 按 `understand` / `blueprint` / `draft` / `review` 分别累计，`llm_usage.by_operation` MUST 按完整操作名分别累计

#### Scenario: provider 不返回缓存字段

- **WHEN** 所用 provider 的响应 usage 中只有 `prompt_tokens` 与 `completion_tokens`
- **THEN** 该调用 MUST 记录 `cache_hit_tokens = 0`、`cache_miss_tokens = prompt_tokens`，任务 MUST 正常继续

#### Scenario: provider 不返回 usage

- **WHEN** 本地模型或 mock 的响应完全没有 usage 信息
- **THEN** 该调用 MUST NOT 产生用量记录，任务 MUST 正常继续

### Requirement: 任务详情透出 LLM 用量

任务详情 API 响应 MUST 包含 `llm_usage` 字段，结构含 `total`、`by_stage`、`by_operation` 三个部分；未产生用量数据的任务 MUST 返回空对象而非报错。

#### Scenario: 详情 API 返回用量

- **WHEN** 客户端请求一个已完成且产生过 LLM 调用的任务详情
- **THEN** 响应 JSON MUST 含 `llm_usage.total.calls >= 1` 及 `by_stage` / `by_operation` 聚合数据
