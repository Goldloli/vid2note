## MODIFIED Requirements

### Requirement: 四档笔记详细程度

该 capability MUST 支持 `concise`（简洁）、`balanced`（适中）、`detailed`（详细）、`thorough`（比较详细）、`exhaustive`（超详细）五档笔记详细程度，默认 MUST 为 `balanced`。其中 `thorough` 与 `exhaustive` 为两个并存的深度档：`thorough` 采用「全文常驻上下文 + 理解→分章深写」引擎（见「比较详细档全文常驻分章深写引擎」要求），`exhaustive` 采用既有 map-reduce 引擎；两者的笔记质量目标相当，`thorough` 的单任务 token 成本与耗时显著低于 `exhaustive`。所选档位 MUST 作为创建任务时的设置快照，同时注入对应提示词分支。详细程度只控制对输入信息的覆盖与展开，MUST NOT 要求模型捏造字幕或讲义中不存在的事实。

#### Scenario: 简洁档只保留核心

- **WHEN** 新任务的详细程度为 `concise`
- **THEN** 提示词 MUST 要求只保留结论、核心概念、关键数据和必要步骤，并主动压缩重复解释和次要示例

#### Scenario: 适中档为默认

- **WHEN** 用户从未修改详细程度
- **THEN** 新任务 MUST 使用 `balanced`，提示词 SHALL 保留主要论点、必要解释、代表性示例和结论

#### Scenario: 详细、比较详细与超详细逐级增加覆盖

- **WHEN** 相同输入分别使用 `detailed`、`thorough` 与 `exhaustive`
- **THEN** `detailed` 提示词 MUST 要求补充上下文、推导、例子和注意事项；`thorough` 与 `exhaustive` 的覆盖要求 MUST 严格高于 `detailed` 且二者质量目标相当，`exhaustive` 的覆盖要求 MUST 不低于 `thorough`

#### Scenario: 比较详细档为高性价比深度档

- **WHEN** 新任务的详细程度为 `thorough`
- **THEN** 系统 MUST 采用「全文常驻分章深写」引擎（全文常驻上下文 + 理解→分章深写），产出质量目标与 `exhaustive` 相当、token 成本与耗时显著更低的深度笔记

#### Scenario: PDF 分支同样应用详细程度

- **WHEN** 任务携带 PDF 参考材料且详细程度为 `exhaustive` 或 `thorough`
- **THEN** 对应提示词分支 MUST 同时包含讲义对照规则和该深度档的约束，MUST NOT 因进入 PDF 分支丢失档位

#### Scenario: 重跑沿用任务快照

- **WHEN** 任务以 `concise` 创建后，全局设置改为 `exhaustive`，用户重跑原任务
- **THEN** 重跑 MUST 继续使用原任务的 `concise` 快照，新建任务才使用 `exhaustive`

## ADDED Requirements

### Requirement: 比较详细档全文常驻分章深写引擎

当笔记详细程度为 `thorough` 时，系统 MUST 采用全文常驻上下文的「理解→分章深写」引擎（双钴），而非分段 map-reduce。该引擎 MUST 依赖 LLM 的长上下文能力把全部有效字幕常驻于每次调用的上下文，MUST NOT 把字幕切段后丢弃或仅以局部摘要可见。生成流程 MUST 为三步：① 全局理解（全文 + 规划指令 → 6-8 章逻辑大纲 JSON 与高置信术语表，恰好 1 次 LLM 调用）；② 分章深写（每章以「system + 全文与规划指令 + 大纲」为稳定前缀、追加本章深写指令发起，每章恰好 1 次 LLM 调用）；③ 机械组装终稿（按大纲顺序拼接章节头部与正文，无 LLM 重写）。术语表 MUST 在理解阶段完成高置信 ASR 纠错并区分概念与产品，分章深写 MUST 强制使用 terminology 中 confidence=high 的 canonical 专名，不得保留已裁决的音译。每章深写的消息前缀 MUST 跨章逐字节稳定（同一蓝图对象的确定性序列化、静态档位指令、确定性清洗函数），以命中支持前缀缓存 provider 的自动缓存。终稿 MUST 经机械组装产生，MUST NOT 再发起整篇 LLM 改写或压缩。当全文长度超过单次上下文安全阈值时，系统 MUST 退回 `exhaustive` 引擎或抛明确错误，MUST NOT 静默截断丢内容。该引擎 MUST 复用既有的提示词注入防护、输出清洗、截图嵌入、思维导图导出、用量上报与进度回调基础设施，且 MUST NOT 捏造字幕或讲义中不存在的事实。

#### Scenario: 全文常驻理解与大纲规划

- **WHEN** 一份有效字幕以 `thorough` 档生成笔记
- **THEN** 系统 MUST 把全部字幕正文作为单次 LLM 调用的上下文，产出含 6-8 个逻辑章节与高置信术语表的规划 JSON，MUST NOT 把字幕切段后仅以局部可见

#### Scenario: 分章深写复用全文前缀

- **WHEN** 大纲规划完成后逐章深写
- **THEN** 每章深写请求的消息前缀 MUST 包含完整全文与大纲且跨章逐字节相同，本章深写指令 MUST 追加在前缀之后，MUST NOT 为每章重发独立的完整 prompt

#### Scenario: 术语前置统一

- **WHEN** 理解阶段建立了高置信术语表
- **THEN** 各章深写 MUST 使用 terminology 中 confidence=high 的 canonical 专名，MUST NOT 保留已被裁决的 ASR 音译或把概念与产品混淆

#### Scenario: 机械组装不再整篇重写

- **WHEN** 全部章节深写完成
- **THEN** 终稿 MUST 由确定性代码按大纲顺序拼接产生，MUST NOT 发起整篇 LLM 改写或压缩

#### Scenario: 超长字幕退回兜底

- **WHEN** `thorough` 任务的字幕全文长度超过单次上下文安全阈值
- **THEN** 系统 MUST 退回 `exhaustive` 引擎或抛明确错误，MUST NOT 静默截断字幕导致内容丢失
