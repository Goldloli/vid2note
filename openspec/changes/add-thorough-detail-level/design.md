## Context

现有「超详细」(exhaustive) 档由 `SimpleProcessor._generate_exhaustive_with_understanding` 实现，是 fork 自 ai_srt2md 的 map-reduce 架构：切段 → 逐段提语义证据 → 全局蓝图 → 逐章深写 → 逐章审校。该架构诞生于 LLM 上下文受限时代，靠"分段 + 层层重发上游产物"工作——把 2.5 万 token 的字幕重复发送成 78.8 万 token 输入，导致单任务约 ¥0.60、35 分钟、34 次串行调用，且对 DeepSeek 自动前缀缓存（best-effort）失效极敏感。

DeepSeek-v4 提供 1M 上下文窗口，2-3 小时课程字幕（约 2.5 万 token）连 3% 都用不满，"全文常驻每次调用上下文"在技术与成本上都可行。已用真实字幕（AI 眼镜课程）实测替代引擎「双钴」（全文常驻 + 理解→分章深写）：9 次调用、¥0.087、3.8 分钟、命中率 86%、产出 27078 字 / 57 个 H3，质量追平 exhaustive（28565 字 / 55 个 H3）。

本设计新增 `thorough` 档承载双钴引擎，与 exhaustive 并存。约束：复用现有 `_call_llm`/`_sanitize_content`/`_clean_markdown_output`/截图/导图/用量上报/进度基础设施；保守 git 档（不提交）；全中文。

## Goals / Non-Goals

**Goals:**
- 新增 `thorough` 档（中文"比较详细"）与双钴引擎，质量目标与 exhaustive 相当，单任务成本降至其约 1/7、耗时降至约 1/9。
- 与 exhaustive 引擎并存，默认档位不变；用户使用后可择优保留。
- 复用现有用量上报（`understand`/`draft` stage）与进度回调，runner 免改。
- 保持输出契约（结构化 Markdown、不捏造、注入防护、截图嵌入兼容）。

**Non-Goals:**
- 不改 exhaustive 引擎、不改默认档位、不引入章节并发、不做历史数据迁移、不改 DB schema、不引入 provider 特定显式缓存 API。

## Decisions

**D1 全文常驻上下文 vs 保留 map-reduce 优化缓存**
选全文常驻。替代方案（前缀稳定化 + 章内消息链）已在上一变更 `optimize-exhaustive-prompt-cache` 落地，命中率仅到约 57%，且因 DeepSeek 缓存 best-effort 不稳（实测同代码同配置可掉到 3%）。根因是"重复发送"本身——全文常驻从结构上消灭重复发送，不依赖缓存稳定即可大幅降本（即使缓存全失效，9 次调用最坏约 ¥0.35，仍低于 exhaustive 的 ¥0.60）。

**D2 理解→分章深写（双钻）vs 单次深写**
选分章。实测单次深写（全文→笔记，1 次调用）只产出 4201 字，模型"写够即止"密度不足；分章深写（理解 1 次 + 每章 1 次）产出 27078 字追平 exhaustive。单次深写作为更轻量的备选保留在设计之外（后续可作"快速档"）。

**D3 章节规划 6-8 章**
实测 8 章产出 27078 字 ≈ exhaustive 28565 字、57 个 H3 ≈ 55。大纲 prompt 硬约束"设计 6-8 个逻辑章节，每章 5-8 个 key_points"，避免章节过少导致密度不足。

**D4 前缀命中构造（跨章稳定前缀）**
每章深写消息链 = `[system, user(全文+规划指令), assistant(大纲), user(本章深写指令)]`。前缀 `[system, 全文+规划指令, 大纲]` 跨所有章节逐字节相同（同一蓝图对象、确定性 `json.dumps`），DeepSeek 多轮缓存规则下第 2 章起命中；实测命中率 86%。

**D5 用量上报 / 进度归类（runner 免改）**
新引擎 `operation_name` 复用现有中文关键词：理解阶段 `"比较详细字幕理解"`、深写阶段 `"比较详细章节初稿(i/n)"`。`runner.classify_llm_operation` 靠"字幕理解"/"章节初稿"子串自动归入 `understand`/`draft` stage；进度回调复用 `understand`/`draft` 两个 phase，`_note_stage_progress` 免改。双钴无独立 blueprint/review 阶段（大纲并入理解、无独立审校），只用 understand+draft。

**D6 术语前置统一（修验证瑕疵）**
理解阶段产出 `terminology`（高置信 ASR 纠错，区分概念/产品）；深写指令硬性要求"必须使用 terminology 中 confidence=high 的 canonical 专名"，避免实测中出现的 X-Rail→XREAL、阴谋→INMO 漏纠。

**D7 超长兜底**
双钴依赖全文塞入单次上下文。设阈值（如正文 > 50 万字符 ≈ 30 万 token，远超正常 2-3 小时字幕的 2.5 万），超限时 `process()` 退回 exhaustive 引擎或抛明确错误，避免静默截断丢内容。

**D8 前缀稳定性保障**
`detail_instruction("thorough")` 为纯静态字典查询（同现有四档）；`json.dumps(blueprint, ensure_ascii=False, indent=2)` 对同一对象确定性输出；`_sanitize_content` 为确定性函数——三者保证跨章前缀逐字节稳定。

## Risks / Trade-offs

- **[单次长输出尾部质量下降]** → 分章深写每章聚焦 + 大纲 `key_points` 硬约束每章必展开要点；`max_tokens` 给足（每章 6000）。
- **[长上下文 attention 稀释]** → 2.5 万 token 远小于 1M，影响有限；关键指令与本章 `key_points` 放消息末尾（recency）。
- **[DeepSeek 缓存 best-effort 不稳]** → 调用次数少（9 次 vs 34），对失效鲁棒；最坏全失效约 ¥0.35 仍低于 exhaustive。
- **[thorough 与 exhaustive 并存增加认知负担]** → i18n hint 说明定位（"全文常驻深度引擎，质量近超详细、成本约其 1/7"）；用户对比后择优，后续变更可废弃其一。
- **[超长视频超出单次上下文]** → D7 阈值兜底退回 exhaustive。
- **[质量主观性]** → 本变更不预设取代 exhaustive；以用户实际使用后的并排对比为取舍依据，故两者并存。
