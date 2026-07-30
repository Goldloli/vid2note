# 设计：超详细 prompt 前缀缓存优化

## 背景约束（DeepSeek 官方缓存规则，其他自动前缀缓存 provider 同理）

1. 只匹配**前缀**：后续请求须完整匹配一个已落盘的「缓存前缀单元」。
2. 每次请求的「用户输入结束位置」和「模型输出结束位置」会落盘单元；**下一请求以其为前缀即立即命中**（官方例一，多轮对话模式）。
3. 多次请求间的公共前缀会被检测落盘，但**前两次不命中，第三次起命中**（官方例二）。
4. 缓存「尽力而为」，不保证 100%。

## 现状问题

- `_build_exhaustive_chapter_prompt` / `_build_exhaustive_chapter_review_prompt` 开头两行是 `【阶段：…】\n章节 ID：Cxx`——第二行即分叉，跨章公共内容（蓝图 JSON、固定指令）全部无法成为公共前缀。
- 审校 prompt 把深写 prompt 的全部材料（蓝图 + 章节规划 + 证据 + 原文）加上初稿**原样重发**，头部不同，全按未命中计费。格式修复、术语保真同理。

## 变更 1：prompt 前缀稳定化重排

原则：**同阶段类型的所有调用，前 N 个 token 逐字节相同**。

- 证据提取 prompt（`_build_exhaustive_evidence_prompt`）：固定任务说明（含证据字段要求、ASR 规则、输出契约）前置；`第 i/N 段`、命名空间、边界上下文、本段正文移到末尾。证据调用间公共前缀 = 固定说明部分（第三次起命中）。
- 章节深写 prompt：顺序改为「固定写作要求（含 detail instruction、截图指令）→ 全局蓝图 JSON（跨章不变且最大）→ 章节规划 / 本章证据 / 本章原文 / 章节 ID」。跨章公共前缀 = 固定要求 + 蓝图 JSON，第 3–8 章命中。
- 章节审校相关 prompt：见变更 2，不再独立构造完整 prompt。
- system message 同阶段类型保持一致（现状已满足，不改语义，只核对待机文案稳定）。
- `json.dumps(blueprint, ensure_ascii=False, indent=2)` 输出确定性：`blueprint_data` 由 `_parse_exhaustive_blueprint` 构造，键序固定，天然满足逐字节稳定。

## 变更 2：章内消息链（draft → review → repairs）

每章一条独立消息链，不跨章累积：

```
messages = [
  {"role": "system", "content": <章节作者 system>},
  {"role": "user",   "content": <深写 prompt>},            # 调用 1：深写
  {"role": "assistant", "content": <初稿>},
  {"role": "user",   "content": <增量审校指令>},            # 调用 2：审校
  {"role": "assistant", "content": <审校稿>},
  {"role": "user",   "content": <增量格式修复指令>},         # 调用 3*：按需
  ...                                                      # 调用 4*：术语保真，按需
]
```

- 审校的增量指令只含「审校规则 + 输出契约 + 待审校内容即上方初稿」；蓝图、证据、原文不再重发——它们已完整存在于链内前缀中，按规则 2 立即命中（不必等第三次）。
- 格式修复、术语保真的增量指令同理接链尾；修复后的输出替换链尾 assistant 内容继续往下接（每章链内顺序追加，不需要重写历史）。
- 蓝图 JSON 修复 / 覆盖修复、证据 ID 修复：同样接在各自首次调用的链尾（`[system, user(原 prompt), assistant(原输出), user(修复指令)]`），修复指令不再重发全部证据/首次输出全文（证据已在链内）。
- `_call_llm` 签名不变；由调用方构造 messages 列表传入，无需改 adapter。

## 语义等价性论证

现状审校 = `[system(审校), user(蓝图+规划+证据+初稿+原文+规则)]`；链式 = 同样信息分布在 `[system(作者), user(深写 prompt 含蓝图/规划/证据/原文), assistant(初稿), user(规则)]`。模型可见信息完全一致，仅 role 分布与顺序不同。既有单测将以 RecordingLLM 断言消息结构与增量指令内容，并以同一桩验证终稿不变量（章节结构校验、ID 覆盖校验、机械组装）不受影响。

## 不变量（必须保持）

- 所有机械校验：证据 ID 命名空间检查、蓝图 JSON 解析、证据覆盖（missing/unknown）、章节恰好一个 H2、终稿 1 H1 + ≥3 H2、内部分析标记泄漏检测——全部原样保留。
- 失败语义：首次输出为空、修复后仍不合格 → 抛同样的 RuntimeError；max_tokens / timeout 不变。
- `_clean_markdown_output`、标题替换、机械术语兜底、机械组装零改动。

## 度量

以 `llm_usage` 观测数据对比同档位任务：核心指标 = `by_stage.review.cache_hit_tokens`（应从 ~0 升至接近该阶段输入总量）、`by_stage.draft.cache_hit_tokens`（第 3 章起命中蓝图前缀）、总计 `cache_miss_tokens` 下降幅度。证据阶段因正文逐块不同，仅固定说明部分可命中，预期收益小。
