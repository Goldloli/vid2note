## ADDED Requirements

### Requirement: 笔记生成的 LLM 调用支持用量上报

笔记生成的 LLM 调用漏斗 MUST 支持可选的用量上报回调：每次调用成功后，若 LLM 适配器留有最近一次调用的 usage 且已注入回调，MUST 以操作名和归一化 usage 调用该回调。回调失败 MUST NOT 中断笔记生成。未注入回调或适配器无 usage 时，生成行为 MUST 与现状完全一致。

#### Scenario: 注入回调后逐次上报

- **WHEN** 以 `usage_callback` 构造处理器并执行包含多次 LLM 调用的生成
- **THEN** 每次调用 MUST 产生恰好一次回调，携带本次的 `operation_name` 与归一化 usage dict

#### Scenario: 回调异常不中断

- **WHEN** `usage_callback` 抛出异常
- **THEN** 处理器 MUST 记录日志并继续生成，MUST NOT 让任务因用量采集失败而失败

### Requirement: LLM 适配器暂存归一化 usage

OpenAI 兼容适配器 MUST 在每次 `chat()` 成功后把响应 usage 归一化为 `{prompt_tokens, completion_tokens, cache_hit_tokens, cache_miss_tokens}` 并暂存于实例属性 `last_usage`，MUST NOT 改变 `chat()` 的返回签名。DeepSeek 的 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` 与 OpenAI 系的 `prompt_tokens_details.cached_tokens` MUST 映射到统一字段。

#### Scenario: DeepSeek 缓存字段映射

- **WHEN** 响应 usage 含 `prompt_cache_hit_tokens = 100`、`prompt_cache_miss_tokens = 900`
- **THEN** `last_usage` MUST 为 `{prompt_tokens: 1000, completion_tokens: <值>, cache_hit_tokens: 100, cache_miss_tokens: 900}`

#### Scenario: 无缓存字段时未命中兜底

- **WHEN** 响应 usage 仅含 `prompt_tokens = 500` 与 `completion_tokens`
- **THEN** `last_usage.cache_hit_tokens` MUST 为 0 且 `cache_miss_tokens` MUST 为 500
