## MODIFIED Requirements

### Requirement: 四档笔记详细程度

该 capability MUST 支持 `concise`（简洁）、`balanced`（适中）、`detailed`（详细）、`exhaustive`（超详细）四档笔记详细程度，默认 MUST 为 `balanced`。新任务与用户界面 MUST NOT 再提供 `thorough`；历史任务的 `thorough` 快照在读取和重跑时 MUST 兼容映射为 `exhaustive`，不得因此无法访问既有产物。所选档位 MUST 作为创建任务时的设置快照，同时注入无 PDF 的 `generate_directly` 与有 PDF 的 `generate_with_pdf_reference` 提示词分支。详细程度只控制对输入信息的覆盖与展开，MUST NOT 要求模型捏造字幕或讲义中不存在的事实。

#### Scenario: 简洁档只保留核心

- **WHEN** 新任务的详细程度为 `concise`
- **THEN** 提示词 MUST 要求只保留结论、核心概念、关键数据和必要步骤，并主动压缩重复解释和次要示例

#### Scenario: 适中档为默认

- **WHEN** 用户从未修改详细程度
- **THEN** 新任务 MUST 使用 `balanced`，提示词 SHALL 保留主要论点、必要解释、代表性示例和结论

#### Scenario: 详细与超详细逐级增加覆盖

- **WHEN** 相同输入分别使用 `detailed` 与 `exhaustive`
- **THEN** 两者提示词 MUST 分别要求补充上下文、推导、例子和注意事项，以及尽量完整的推导链、反例、边界和术语说明；`exhaustive` 的覆盖要求 MUST 严格高于 `detailed`

#### Scenario: 历史比较详细任务兼容重跑

- **WHEN** 历史任务快照为 `thorough` 且用户查看或重跑该任务
- **THEN** 既有产物 MUST 可继续访问，重跑 MUST 使用 `exhaustive` 处理器，新建任务接口 MUST NOT 再接受 `thorough`

#### Scenario: PDF 分支同样应用详细程度

- **WHEN** 任务携带 PDF 参考材料且详细程度为 `exhaustive`
- **THEN** `generate_with_pdf_reference` 提示词 MUST 同时包含讲义对照规则和超详细约束，MUST NOT 因进入 PDF 分支丢失档位

#### Scenario: 重跑沿用任务快照

- **WHEN** 任务以 `concise` 创建后，全局设置改为 `exhaustive`，用户重跑原任务
- **THEN** 重跑 MUST 继续使用原任务的 `concise` 快照，新建任务才使用 `exhaustive`

### Requirement: 超详细长字幕分层理解与全局综合

系统 MUST 在固定内容长度限制之前将全部有效字幕按自然边界分配到 source chunk。每个非空 source chunk MUST 先生成带稳定证据 ID、原文摘录和来源段标识的语义证据包；全部证据包 MUST 进入一次全局知识建模，形成课程主线、带置信度的全局术语表、概念关系、去重后的章节蓝图，以及每章的证据 ID 映射。术语表 MUST 只结合跨段证据统一高置信专名，无法确认时 MUST 保留不确定性。后端 MUST 机械验证每个证据 ID 至少被一个章节分配。每章 MUST 参考全局蓝图、术语表和对应证据包深写；MUST NOT 为每章重复发送与本章无关的完整 source chunk，最终正文 MUST 按主题和论证关系组织。

#### Scenario: 后半段独立主题参与全局结构
- **WHEN** 两小时字幕的后半段包含前半段未出现的重要主题
- **THEN** 后半段 MUST 形成语义证据并进入全局蓝图，对应主题 MUST 被分配到最终章节，MUST NOT 在固定字符位置被截断

#### Scenario: 跨分段重复主题合并
- **WHEN** 同一概念在多个不连续 source chunk 中反复出现并逐步补充定义、案例和限制
- **THEN** 全局蓝图 MUST 将相关证据 ID 归并到同一逻辑章节，最终笔记 MUST 综合这些材料且 MUST NOT 产生多个互相割裂的重复章节

#### Scenario: 证据包保留追溯语境
- **WHEN** 某项证据被分配给一个章节
- **THEN** 证据包 MUST 含足以核验该项的原文摘录和 source chunk 标识，章节调用 MUST 只携带本章证据及稳定全局前缀，MUST NOT 重发全部原始字幕

#### Scenario: 蓝图漏分配证据
- **WHEN** 全局蓝图首次输出未把某个语义证据 ID 分配给任何章节
- **THEN** 系统 MUST 请求只包含缺失 ID 与目标章节映射的紧凑补丁并再次机械验证，MUST NOT 默认重写整份蓝图；仍未分配时 MUST 明确失败

#### Scenario: ASR 音译混淆概念与产品
- **WHEN** 多个字幕段以不同音译提到同一专名且上下文能够高置信区分其类型与功能
- **THEN** 全局蓝图 MUST 建立统一 canonical 术语，逐章生成 MUST 使用该术语，MUST NOT 用外部常识擅自猜测

### Requirement: 超详细终稿按需审计修复并无损组装

系统 MUST 按全局蓝图逐章生成初稿，每章输出 MUST 携带可由代码剥离的证据覆盖声明。代码 MUST 先验证章节结构和已分配证据覆盖，再对全部章节执行一次只返回紧凑 JSON 问题列表的全局审计；审计 MUST NOT 返回或重写完整章节。只有被判定存在事实、证据、术语、重复或结构问题的章节才可进入定向修复，未命中问题的章节 MUST 原样进入终稿。系统 MUST 按蓝图顺序机械组装章节，MUST NOT 再让 LLM 全篇重写或压缩。

#### Scenario: 无问题章节不触发二次生成
- **WHEN** 某章通过确定性门禁且全局审计未报告该章问题
- **THEN** 该章 MUST 直接进入终稿，MUST NOT 发起逐章全文审校调用

#### Scenario: 初稿遗漏已分配证据
- **WHEN** 章节覆盖声明或全局审计表明某个已分配的高价值证据未被表达
- **THEN** 系统 MUST 仅对该章发起定向修复，修复后再次验证覆盖，MUST NOT 重写其他合格章节

#### Scenario: 全局审计只返回问题列表
- **WHEN** 所有章节初稿已完成
- **THEN** 审计输出 MUST 为包含章节 ID、问题类型和修复指令的紧凑结构化数据，MUST NOT 包含完整章节 Markdown

#### Scenario: 终稿结构门禁
- **WHEN** 审计与必要修复完成
- **THEN** 终稿 MUST 包含唯一 H1、多个有正文的逻辑章节和有效 Markdown 层级，且 MUST NOT 泄漏内部章节 ID、证据 ID、证据模板、覆盖声明或审计指令

#### Scenario: 不强制不存在的维度
- **WHEN** 原材料对某个观点没有数据、反例或适用边界
- **THEN** 系统 MUST 忠实省略缺失维度，MUST NOT 为满足固定写作模板而补充外部事实或重复已有结论

## ADDED Requirements

### Requirement: 超详细成本与调用效率可验收

超详细实现 MUST 保留逐次 usage 上报，并 SHALL 在同模型、相近时长长视频上相对 2026-08-04 基线减少 LLM 调用、总 Token、估算费用和笔记节点耗时。优化 MUST NOT 通过遗漏后半段主题、关闭统计或降低输出语言质量达成。

#### Scenario: 长视频优化验收
- **WHEN** 使用 DeepSeek `deepseek-v4-flash` 对一段约 150 分钟视频生成超详细笔记
- **THEN** 任务详情 MUST 可计算调用数、输入/输出 Token 和分阶段费用，且调用数与费用 SHALL 低于基线的 32 次和 ¥0.469

#### Scenario: 质量不以字数替代
- **WHEN** 优化后笔记字数少于基线
- **THEN** 验收 MUST 检查主题覆盖、论证、案例、边界、重复率和内部模板泄漏，MUST NOT 仅因字数减少判定质量下降
