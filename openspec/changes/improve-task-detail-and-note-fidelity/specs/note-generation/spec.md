## ADDED Requirements

### Requirement: 超详细笔记以理解质量为核心

当笔记详细程度为 `exhaustive` 时，系统 MUST 将“超详细”解释为对完整原材料进行充分理解后形成的高质量深度笔记，而不是更长的字幕改写或固定字符比例输出。最终笔记 MUST 准确表达课程的中心问题、核心结论、概念关系、完整论证、关键案例的作用、反例、适用边界、注意事项、术语和可执行结论；系统 MUST NOT 为追求篇幅捏造、使用外部常识补齐或重复同一信息。

#### Scenario: 解释结论及其成立原因
- **WHEN** 原材料包含一个结论以及分散在不同时间段的定义、推导、案例和限制
- **THEN** 最终笔记 MUST 把这些材料组织为连贯论证，说明结论是什么、为什么成立、案例证明什么及其适用边界，MUST NOT 只按时间顺序复述

#### Scenario: 字符比例不作为质量标准
- **WHEN** 一份高信息密度字幕和一份包含大量寒暄、重复或 ASR 噪声的字幕都以 `exhaustive` 生成
- **THEN** 系统 MUST 按各自的有效知识量组织笔记，MUST NOT 以输入输出字符比例决定是否通过或要求模型填充到固定长度

#### Scenario: 不确定材料忠实保留
- **WHEN** 专有名词、数字或语句因 ASR 错误而无法结合上下文可靠确认
- **THEN** 最终笔记 MUST 标记该项存在不确定性，MUST NOT 擅自替换成看似合理但原材料无法支持的内容

### Requirement: 超详细长字幕分层理解与全局综合

系统 MUST 在固定内容长度限制之前将全部有效字幕按自然边界分配到 source chunk。每个非空 source chunk MUST 先生成带稳定证据 ID 的语义证据包；全部证据包 MUST 进入全局知识建模，形成课程主线、带置信度的全局术语表、概念关系、去重后的章节蓝图，以及每章的证据 ID 与 source chunk 映射。术语表 MUST 只结合跨段证据统一高置信专名，MUST 区分概念与产品，无法确认时 MUST 保留不确定性。后端 MUST 机械验证每个证据 ID 至少被一个章节分配。每章 MUST 同时参考全局蓝图、术语表、对应证据与对应完整原始字幕片段进行深写，最终正文 MUST 按主题和论证关系组织，MUST NOT 直接拼接 source chunk 的局部摘要。

#### Scenario: 后半段独立主题参与全局结构
- **WHEN** 两小时字幕的后半段包含前半段未出现的重要主题
- **THEN** 后半段 MUST 形成语义证据并进入全局蓝图，对应主题 MUST 被分配到最终章节，MUST NOT 在固定字符位置被截断

#### Scenario: 跨分段重复主题合并
- **WHEN** 同一概念在多个不连续 source chunk 中反复出现并逐步补充定义、案例和限制
- **THEN** 全局蓝图 MUST 将相关证据 ID 归并到同一逻辑章节，最终笔记 MUST 综合这些材料且 MUST NOT 产生多个互相割裂的重复章节

#### Scenario: 分块边界不决定最终章节
- **WHEN** 一个完整论证跨越两个 source chunk 的边界
- **THEN** 相邻证据包 MUST 保留跨段线索，初稿 MUST 根据全局蓝图把论证恢复为一个连贯章节，MUST NOT 暴露“第几分块”等内部处理结构

#### Scenario: 语义证据有内容但遗漏稳定 ID
- **WHEN** 某个 source chunk 的首次语义证据输出非空但未使用规定证据命名空间
- **THEN** 系统 MAY 执行一次只补充稳定 ID 和结构、不得删除或新增事实的定向修复，并 MUST 再次验证；修复后仍无有效 ID 时 MUST 明确失败

#### Scenario: 蓝图漏分配证据
- **WHEN** 全局蓝图首次输出未把某个语义证据 ID 分配给任何章节
- **THEN** 系统 MUST 定向修复蓝图并再次机械验证，仍未分配时 MUST 明确失败，MUST NOT 继续生成可能缺章的笔记

#### Scenario: 蓝图 JSON 语法错误或中途截断
- **WHEN** 全局蓝图包含规划内容但无法严格解析为完整 JSON
- **THEN** 系统 MUST 基于首次输出和全部语义证据定向修复完整 JSON，并重新执行 schema 与证据覆盖校验，MUST NOT 仅闭合残缺括号或跳过校验

#### Scenario: ASR 音译混淆概念与产品
- **WHEN** 多个字幕段以不同音译提到 Harness Engineering、OpenClaw、Hermes Agent 或 Skill，且上下文能够高置信区分其类型与功能
- **THEN** 全局蓝图 MUST 建立统一 canonical 术语，逐章生成 MUST 使用该术语，MUST NOT 把 Hermes Agent 猜成 Claude / Hailuo、把 Harness Engineering 当作产品或把 Skill 猜成 Store / Studio

#### Scenario: 章节审校后仍残留实体或术语漂移
- **WHEN** 已审校章节仍出现可识别的高置信 ASR 错拼、错误年份或概念 / 产品 / 机制归属混淆
- **THEN** 系统 MUST 对该章执行实体与术语保真审校，MUST 同时参考原始字幕、证据和全局术语表；系统 MAY 在当前章内把直接归错产品的小节移回正确归属，但 MUST NOT 概括、删减或扩写正文事实，且修复后的章节 MUST 重新通过结构门禁

### Requirement: 超详细终稿逐章深写、审校并无损组装

系统 MUST 按全局蓝图逐章生成初稿，并对每章执行独立编辑审校。每章审校 MUST 同时参考该章对应的原始字幕、语义证据、全局蓝图和章节初稿，并从事实忠实度、证据覆盖、章节结构、信息价值和可读性五个维度形成终稿章节。编辑阶段 SHALL 合并逐字重复和空泛表达，但 MUST NOT 删除具有独立信息价值的事实、论证、案例、反例或边界。系统 MUST 按蓝图顺序机械组装审校后的章节，MUST NOT 再让 LLM 全篇重写或压缩。任一阶段输出为空或终稿缺少有效章节结构时，系统 MUST 明确失败。

#### Scenario: 初稿遗漏已分配的高价值证据
- **WHEN** 全局蓝图把某个高价值证据 ID 分配给章节，但该章初稿未表达其核心内容
- **THEN** 该章编辑审校 MUST 在终稿章节中恢复该内容或明确说明原材料不确定，MUST NOT 静默交付遗漏内容的笔记

#### Scenario: 全篇编辑不得再次压缩章节
- **WHEN** 所有章节均已完成深写和独立审校
- **THEN** 系统 MUST 用确定性代码按蓝图顺序组装文档头部与章节，MUST NOT 发起一次整篇 LLM 改写而重新丢失已展开的信息

#### Scenario: 终稿结构门禁
- **WHEN** 编辑审校完成
- **THEN** 终稿 MUST 包含唯一 H1、多个使用蓝图正式标题且有正文的逻辑章节和有效 Markdown 层级，且 MUST NOT 泄漏 `C06` 等内部章节 ID、语义证据模板、证据 ID 清单或内部审校指令

#### Scenario: 审校章节仅泄漏内部证据编号
- **WHEN** 章节已经通过事实审校且结构完整，但正文仍包含内部 evidence ID
- **THEN** 系统 MAY 执行一次只删除内部标记、不得概括或压缩正文的定向格式修复，并 MUST 重新通过章节结构门禁后才发布

### Requirement: 截图产物路径规范与受控访问

截图成功生成后，任务记录中的 `screenshot_paths` MUST 保存为相对 `DATA_ROOT` 的规范 POSIX 路径，路径中 MUST NOT 含 `..`。Markdown 可继续保存相对笔记目录的图片引用；系统 MUST 能将每个已登记截图通过当前任务的受控产品端点按索引读取，且 MUST 继续执行任务归属与安全路径检查。

#### Scenario: 新截图登记为规范路径
- **WHEN** 笔记节点在 `screenshots/<task_id>/shot_120.png` 成功截帧并登记产物
- **THEN** 任务记录 MUST 保存 `screenshots/<task_id>/shot_120.png`，MUST NOT 保存 `notes/<task_id>/../../screenshots/...`

#### Scenario: 历史非规范路径仍可读取
- **WHEN** 历史任务已保存含 `..` 的截图路径，但该路径解析后仍位于 `DATA_ROOT` 且文件存在
- **THEN** 产品端点 MUST 在通过安全路径校验后继续提供该图片，前端 MUST 能按当前任务截图索引显示
