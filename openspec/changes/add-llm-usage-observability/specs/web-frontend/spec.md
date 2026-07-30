## ADDED Requirements

### Requirement: 任务详情页展示 LLM 消耗

任务详情页 MUST 在任务产生过 LLM 用量数据时展示「LLM 消耗」区块：按阶段（证据理解、全局蓝图、章节深写、章节审校、思维导图、其他）以表格展示调用次数、输入 tokens、缓存命中 tokens、缓存未命中 tokens、输出 tokens 与输入命中率，并含总计行。任务无用量数据时 MUST NOT 渲染该区块。数字 MUST 使用等宽对齐样式，文案 MUST 提供中英文。

#### Scenario: 有用量的任务展示分阶段表格

- **WHEN** 用户打开一个 `llm_usage.total.calls > 0` 的任务详情
- **THEN** 页面 MUST 显示「LLM 消耗」区块，每个有调用的阶段各占一行，总计行与各阶段行数值一致勾稽

#### Scenario: 无用量任务不显示区块

- **WHEN** 用户打开一个无 `llm_usage` 数据的历史任务详情
- **THEN** 页面 MUST NOT 显示「LLM 消耗」区块，其余内容不受影响
