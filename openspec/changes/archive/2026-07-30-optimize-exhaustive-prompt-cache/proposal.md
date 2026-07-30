## Why

超详细档位一次任务 20+ 次 LLM 调用，实测单日输入数百万 tokens 而缓存命中率仅约 13%。根因是 prompt 结构不友好前缀缓存：章节 prompt 第二行即出现分叉内容（章节 ID），跨章完全相同的大块内容（全局蓝图 JSON、固定指令）被放在变量之后；审校/修复调用把上游全部输入原样重发且头部不同，无法命中 DeepSeek 等厂商的自动前缀缓存（前缀单元完整匹配才命中）。用量观测功能（`add-llm-usage-observability`）已就绪，本变更的收益可度量。

## What Changes

- 前缀稳定化重排：超详细各阶段 prompt 统一改为「逐字节稳定内容在前、每次调用不同的内容在末尾」。固定写作/审校指令与全局蓝图 JSON + 术语表前置，章节 ID、章节规划、本章证据与原文等变量压到 prompt 尾部。
- 章内消息链：章节审校、格式修复、术语保真不再单发完整 prompt，而是在本章深写调用的消息链尾追加增量指令（`[system, user(深写 prompt), assistant(初稿), user(增量审校指令)]`），使上游输入与输出整体成为可命中的缓存前缀单元。证据 ID 修复、蓝图 JSON/覆盖修复同理接在各自调用链尾。
- 每章仍起独立消息链，不跨章累积对话历史；所有机械校验（证据 ID、蓝图 JSON/覆盖、章节结构、终稿结构）与失败语义保持不变，校验不过仍按现有路径抛错或触发链尾修复。
- 该优化为纯 prompt 工程：不改 adapter 层、不改生成阶段划分与 max_tokens/timeout，对不支持缓存的 provider 行为与现状一致（只是消息结构变化），输出契约不变。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `note-generation`: 超详细链路的 prompt 组装顺序与多轮消息结构变化，要求保持前缀稳定与既有校验契约。

## Impact

- 后端：`SimpleProcessor` 的 `_build_exhaustive_*_prompt` 系列组装顺序、`_generate_exhaustive_with_understanding` 中审校/修复调用的消息构造；相关测试更新。
- 预期效果（以用量观测数据验证）：DeepSeek 等支持自动前缀缓存的 provider 上，审校/修复调用的上游输入转为缓存命中价，蓝图等跨章稳定前缀在第 3 次起命中；总输入 tokens 基本持平或略升，未命中输入 tokens 显著下降。
- 兼容性：对 Anthropic 式显式缓存标记之外的自动前缀缓存 provider（DeepSeek/OpenAI/通义/智谱/豆包/Kimi）同步受益；无缓存机制的 provider（Ollama 本地）无回归。
- 风险：DeepSeek 缓存「尽力而为」不保证 100% 命中；链式消息使审校看到深写原始指令（语义等价于现有重发，已验证无行为差异）。

## Non-goals

- 不改变超详细的阶段划分（证据 → 蓝图 → 深写 → 审校 → 组装）、调用次数上限与机械校验规则。
- 不引入 provider 特定的显式缓存 API（如 Anthropic cache_control、Kimi context cache 管理接口）。
- 不做并发调用、不减少章节数、不降低 max_tokens 等「省量」手段——本变更只解决「重复输入按全价计费」问题。
- 不做价格/成本配置；收益以观测功能的未命中输入 tokens 与命中率对比呈现。
