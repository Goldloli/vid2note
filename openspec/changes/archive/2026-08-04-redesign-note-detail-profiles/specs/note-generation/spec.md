## MODIFIED Requirements

### Requirement: 笔记生成主干与 ai_srt2md prompt 库复用

该 capability SHALL 沿用基底 ai_srt2md 的字幕解析、纯文本提取、提示词注入防护、PDF 参考消费、restructure 整理原则与 Markdown 清洗能力。`concise`、`balanced`、`detailed` SHALL 使用共享的“全量内容地图 → 档位证据选择与章节蓝图 → 分批章节写作 → 确定性门禁 → 按策略审计/局部修复”主干；`exhaustive` SHALL 继续使用其分段证据、全局蓝图、逐章写作和按需修复主干。携带 PDF 时，内容地图与写作阶段 MUST 消费 `generate_with_pdf_reference` 的讲义对照原则；无 PDF 时 MUST 消费 `generate_directly` / restructure 的整理原则。LLM 原始输出 MUST 经清洗后落盘。

#### Scenario: 无 PDF 的三档任务先理解后写作

- **WHEN** 无 PDF 的 `concise`、`balanced` 或 `detailed` 任务处理长字幕
- **THEN** 系统 MUST 先生成可解析的全量内容地图，再按档位生成章节，MUST NOT 直接把固定长度字幕交给一次性终稿提示词

#### Scenario: 携带 PDF 的三档任务保留讲义参考

- **WHEN** `concise`、`balanced` 或 `detailed` 任务携带 PDF 参考材料
- **THEN** 内容地图与章节写作 MUST 以字幕为事实主来源、以讲义为结构与术语校准来源，MUST NOT 因进入新主干丢失 PDF 参考

#### Scenario: 重组套用结构化整理原则

- **WHEN** 任一档位执行章节写作
- **THEN** 写作 SHALL 去除问候语、口头禅与无新增信息的重复，忠实保留该档位选择的概念、数据、方法、案例与边界，并输出规范 Markdown

#### Scenario: 清洗 LLM 输出的代码块包裹

- **WHEN** 内容地图修复以外的 LLM Markdown 输出被代码块围栏包裹
- **THEN** 落盘前 MUST 剥离围栏，最终 Markdown 首尾 MUST NOT 残留代码块标记

### Requirement: 四档笔记详细程度

该 capability MUST 支持 `concise`（简洁）、`balanced`（适中）、`detailed`（详细）、`exhaustive`（超详细）四档，默认 MUST 为 `balanced`。新任务和用户界面 MUST NOT 提供 `thorough`；历史 `thorough` MUST 兼容映射为 `exhaustive`。四档 MUST 共享事实忠实与全局规划原则，但 SHALL 通过证据重要度、章节范围、写作批次、示例政策和审计强度形成逐级增加的覆盖与成本阶梯。所选档位 MUST 作为创建任务时的设置快照，MUST NOT 要求模型捏造字幕或讲义中不存在的事实。

#### Scenario: 简洁档只选择决策关键证据

- **WHEN** 新任务详细程度为 `concise`
- **THEN** 内容地图和终稿 MUST 聚焦 18 条关键结论、核心概念、关键数据、必要步骤和风险证据，主动排除非必要案例与重复解释，并以 3～4 个主要章节、每章 350～650 字为目标

#### Scenario: 适中档为默认且覆盖主要证据

- **WHEN** 用户从未修改详细程度
- **THEN** 新任务 MUST 使用 `balanced`，选择 30 条关键、高价值与代表性补充证据，并保留代表性案例、必要解释和一层推导，以 5～6 个主要章节、每章 550～900 字为目标

#### Scenario: 详细档保留系统推导和边界

- **WHEN** 新任务详细程度为 `detailed`
- **THEN** 终稿 MUST 选择 50 条关键/高价值/补充及重要上下文证据，保留定义、推导、重要案例、数据、适用边界和注意事项，以 6～8 个主要章节、每章 850～1400 字为目标

#### Scenario: 超详细覆盖严格高于详细

- **WHEN** 相同输入分别使用 `detailed` 与 `exhaustive`
- **THEN** `exhaustive` MUST 继续覆盖所有非噪声证据并使用更强的分段理解与逐章审计策略，覆盖要求 MUST 严格高于 `detailed`

#### Scenario: 历史比较详细任务兼容重跑

- **WHEN** 历史任务快照为 `thorough` 且用户查看或重跑
- **THEN** 既有产物 MUST 可继续访问，重跑 MUST 使用 `exhaustive`，新建任务 MUST NOT 接受 `thorough`

#### Scenario: 重跑沿用任务快照

- **WHEN** 任务以 `concise` 创建后全局设置改为 `exhaustive`
- **THEN** 重跑 MUST 继续使用原任务的 `concise` 快照，新任务才使用 `exhaustive`

### Requirement: 长字幕分块处理

对于超过旧单次直接生成安全阈值的长字幕，该 capability MUST 通过全量内容地图或分段证据提取消费全部有效文本，再生成一份连贯 Markdown；MUST NOT 以固定字符截断后直接生成终稿。三种非超详细档位在安全全文上限内 SHALL 优先使用一次完整内容地图和稳定消息前缀；超过安全全文上限时 MUST 分段处理或明确失败。`exhaustive` SHALL 继续按自然边界分段提取证据。

#### Scenario: 短字幕不增加不必要调用

- **WHEN** 输入字幕小于直接处理阈值且不需要分层理解
- **THEN** 系统 MAY 使用一次生成，但仍 MUST 应用档位约束、注入防护和 Markdown 清洗

#### Scenario: 三档长字幕全部进入内容地图

- **WHEN** `concise`、`balanced` 或 `detailed` 输入超过旧 50,000 字符阈值但未超过安全全文上限
- **THEN** 完整正文 MUST 进入内容地图调用，MUST NOT 只保留前 50,000 字符

#### Scenario: 超过全文安全上限不静默截断

- **WHEN** 三档输入超过安全全文上限
- **THEN** 系统 MUST 将全部内容分配到分段理解阶段或返回明确错误，MUST NOT 静默丢弃尾部内容

#### Scenario: 分层结果合并为连贯笔记

- **WHEN** 多批章节写作完成
- **THEN** 系统 MUST 按蓝图顺序机械合并为一份层级连贯的 Markdown，MUST NOT 再让模型全篇重写或压缩

## ADDED Requirements

### Requirement: 三档全量内容地图与证据映射

`concise`、`balanced`、`detailed` 的长字幕生成 MUST 先形成严格可解析的全量内容地图。内容地图 MUST 至少包含标题、课程总览、术语、稳定证据 ID、证据重要度、证据类型、可核验摘录、置信度、章节 ID、章节目标和章节证据映射。三档 MUST 分别固定选择 18、30、50 条独立证据，每条证据 MUST 且只能映射到一个章节。代码 MUST 拒绝未知证据 ID；章节逻辑错误 MUST 只请求一次紧凑映射补丁，并机械清理重复/未知映射、补齐漏挂 ID。

#### Scenario: 后半段主题进入蓝图

- **WHEN** 长字幕后半段出现前半段没有的重要主题
- **THEN** 该主题 MUST 形成证据并被映射到至少一个章节，MUST NOT 因旧清洗上限被丢弃

#### Scenario: 内容地图 JSON 不合法

- **WHEN** 首次内容地图输出无法严格解析
- **THEN** 系统 MUST 沿原消息链请求一次只修复结构的 JSON；修复后仍不合法则 MUST 明确失败

#### Scenario: 任务标题帮助校正 ASR 专名

- **WHEN** 上传任务标题包含与字幕上下文一致的产品或人物专名
- **THEN** 内容地图 MAY 将标题作为术语校正线索，但 MUST NOT 把标题单独当作数据、结论、案例或其他事实证据

#### Scenario: 章节映射补丁有机械缺口

- **WHEN** 章节映射补丁重复、遗漏或包含未知证据 ID
- **THEN** 代码 MUST 删除重复与未知 ID，并把漏挂证据分配到当前证据最少的章节，MUST NOT 为该机械缺口新增 LLM 调用

#### Scenario: 档位按重要度选择证据

- **WHEN** 内容地图包含 critical、high、supporting 和 context 证据
- **THEN** 三档 MUST 按各自策略选择证据，且较高档位 MUST NOT 比较低档位覆盖更少的 critical/high 证据

### Requirement: 三档分批写作、确定性门禁与按需修复

三档章节写作 MUST 使用稳定的完整内容地图消息前缀，并只在链尾追加当前章节批次。每个章节 MUST 输出可机械剥离的证据覆盖声明。代码 MUST 检查唯一 H1、预期 H2、空章节、重复标题、证据映射、内部模板泄漏与 Markdown 围栏。`concise` SHALL 只在门禁失败时修复；`balanced` SHALL 在门禁失败或关键低置信风险出现时审计；`detailed` MUST 执行一次只返回 JSON 问题列表的全局审计。只有问题章节可被重写；详细档审计 MUST 忽略风格润色、轻微重复、篇幅偏好与可选补充，且每次最多选择两个不同章节进行修复。

#### Scenario: 简洁档批量生成章节

- **WHEN** 简洁蓝图包含 3～4 章
- **THEN** 系统 SHALL 在一个写作批次中生成全部章节，并在门禁通过时不发起语义审计

#### Scenario: 详细档执行紧凑全局审计

- **WHEN** 详细档全部章节初稿完成
- **THEN** 系统 MUST 发起一次只返回章节 ID、问题类型和修复指令的 JSON 审计，MUST NOT 请求完整笔记重写

#### Scenario: 详细档限制审计重写放大

- **WHEN** 详细档审计返回多项问题或只属于表达润色、轻微重复、篇幅偏好、可选补充的问题
- **THEN** 系统 MUST 只保留至多两个不同章节的 `critical`/`high` 白名单问题，并 MUST 丢弃不影响事实覆盖与结构正确性的风格问题

#### Scenario: 合格章节不被重写

- **WHEN** 某章通过确定性门禁且审计未报告该章问题
- **THEN** 该章 MUST 原样进入终稿，MUST NOT 产生章节修复调用

#### Scenario: 最终产物不泄漏内部标记

- **WHEN** 三档任一任务完成
- **THEN** 最终 Markdown MUST NOT 包含证据 ID、覆盖声明、内部阶段说明或审计指令

### Requirement: 六视频真实基准与全量回归验收

本变更 MUST 在生产代码改动前完成简洁、适中、详细各一条约 150 分钟视频基线；改动后 MUST 使用另外三条与对应基线时长差不超过 1% 的视频复测。每个任务 MUST 记录源时长、任务 ID、逐次 usage、调用数、费用、ASR 与笔记耗时、字幕/笔记字符数和 Markdown 结构指标。最终实现 MUST 通过后端全量测试、前端构建和 OpenSpec 校验。

#### Scenario: 基线先于实现改动

- **WHEN** 开始修改三档生产生成代码
- **THEN** 三条旧实现基线 MUST 已完成或明确记录不可恢复的外部阻塞，且已有报告可区分基线和复测

#### Scenario: 复测使用时长近似的不同视频

- **WHEN** 三档新实现进入真实复测
- **THEN** 每档 MUST 使用与其基线不同且时长差不超过 1% 的视频，并同时报告绝对指标与每万字幕字符归一化指标

#### Scenario: 不以字数单独判断质量

- **WHEN** 新实现笔记长度与基线不同
- **THEN** 质量判断 MUST 同时检查主题/关键证据抽样、章节结构、重复、事实忠实和内部模板泄漏，MUST NOT 仅以字数判定优劣

#### Scenario: 全量质量门禁

- **WHEN** 实现和六视频复测完成
- **THEN** 后端全量 pytest、前端生产构建和 `openspec validate` MUST 全部成功；任何失败 MUST 被修复或明确报告为阻塞
