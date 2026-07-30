## ADDED Requirements

### Requirement: 超详细 prompt 前缀稳定

超详细链路中同一阶段类型的多次 LLM 调用，其消息前缀 MUST 由逐字节稳定的内容构成：固定指令与跨调用不变的大块内容（如全局蓝图 JSON）在前，每次调用不同的内容（章节 ID、章节规划、本章证据、本章原文、段序号、命名空间、边界上下文、字幕正文）在末尾。重排 MUST NOT 改变任何阶段的生成契约、机械校验与失败语义。

#### Scenario: 章节深写 prompt 的顺序

- **WHEN** 构造第 3 章与第 5 章的深写 prompt
- **THEN** 两个 prompt 从首字符到全局蓝图 JSON 结束 MUST 逐字节相同，章节规划、证据与原文 MUST 出现在蓝图之后

### Requirement: 章内审校与修复使用消息链

章节审校、章节格式修复、术语保真 MUST 在本章深写调用的消息链尾以增量指令发起：消息列表依次包含深写的 system/user 消息、深写输出（assistant）、增量指令（user），MUST NOT 把蓝图、证据、原文、初稿作为新的完整 prompt 重发。每章 MUST 使用独立消息链，MUST NOT 跨章累积对话历史。增量指令 MUST 保留既有审校规则与输出契约，机械校验与失败语义 MUST 与单发 prompt 时一致。

#### Scenario: 审校调用不重发上游材料

- **WHEN** 某章深写成功后发起审校
- **THEN** 审校请求的消息 MUST 以深写请求的完整消息列表为前缀，审校 user 消息 MUST NOT 包含全局蓝图 JSON 或本章原始字幕全文

#### Scenario: 条件修复接在链尾

- **WHEN** 章节审校稿触发格式修复与术语保真
- **THEN** 两次调用 MUST 依次接在同一章的消息链尾，修复后的输出 MUST 作为链的最新 assistant 内容参与后续校验

### Requirement: 证据与蓝图修复使用消息链

语义证据 ID 修复、蓝图 JSON 修复、蓝图覆盖修复 MUST 接在各自首次调用的消息链尾，修复指令 MUST NOT 重发首次输出全文或全部证据全文（内容已在链内前缀中）。修复失败判定与抛错行为 MUST 与现状一致。

#### Scenario: 证据 ID 修复

- **WHEN** 第 i 段证据首次输出缺少命名空间 ID
- **THEN** 修复请求 MUST 以 `[system, user(原证据 prompt), assistant(首次输出), user(修复要求)]` 结构发起，修复后仍缺 ID 时 MUST 抛出与现状相同的错误
