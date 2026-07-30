## MODIFIED Requirements

### Requirement: 8 家 LLM 适配与引擎、模型可配

该 capability SHALL 通过统一的 `BaseLLM` 门面适配 8 家内置 LLM（DeepSeek / 通义千问 / 智谱 GLM / Moonshot-Kimi / 百度千帆 / 豆包 / MiniMax / Ollama）以及一个 `custom` OpenAI Chat Completions 兼容槽位。默认 LLM 引擎 MUST 为 DeepSeek、默认模型 MUST 为 `deepseek-v4-flash`。每个 provider 的模型、Base URL 与凭证 SHALL 独立可配，用户填写的非空模型 ID MUST 优先于内置建议值；配置变更 MUST 仅作用于其后新建的任务，不得回溯覆盖历史笔记。

#### Scenario: 默认引擎与模型为 DeepSeek deepseek-v4-flash

- **WHEN** 用户从未修改 LLM 引擎与模型设置而创建笔记生成任务
- **THEN** 该 capability MUST 使用 DeepSeek 引擎与 `deepseek-v4-flash` 模型完成笔记生成

#### Scenario: 设置切换引擎与自定义模型

- **WHEN** 用户把 Qwen 模型改为一个有效的自定义模型 ID、设为默认并新建任务
- **THEN** 该 capability MUST 通过 Qwen 适配器使用用户填写的精确模型 ID，MUST NOT 回退内置建议模型

#### Scenario: 九种槽位均走统一门面

- **WHEN** 笔记生成在任一内置 provider 或 `custom` 下运行
- **THEN** 调用方 MUST 只依赖统一的 `BaseLLM` 门面，provider 的协议差异 MUST 封装在适配器内部

#### Scenario: 自定义 OpenAI 兼容服务

- **WHEN** 用户选择已配置名称、Base URL、模型和可选密钥的 `custom` 槽位
- **THEN** 该 capability MUST 向该 Base URL 的 Chat Completions 兼容接口发起请求

#### Scenario: 引擎与模型切换不影响历史任务

- **WHEN** 用户在已有任务 A（笔记已生成）之后切换引擎/模型，再新建任务 B
- **THEN** 任务 B SHALL 使用新引擎/模型，任务 A 的既有笔记 MUST NOT 被自动重跑或覆盖

## ADDED Requirements

### Requirement: 四档笔记详细程度

该 capability MUST 支持 `concise`（简洁）、`balanced`（适中）、`detailed`（详细）、`exhaustive`（超详细）四档笔记详细程度，默认 MUST 为 `balanced`。所选档位 MUST 作为创建任务时的设置快照，同时注入无 PDF 的 `generate_directly` 与有 PDF 的 `generate_with_pdf_reference` 提示词分支。详细程度只控制对输入信息的覆盖与展开，MUST NOT 要求模型捏造字幕或讲义中不存在的事实。

#### Scenario: 简洁档只保留核心

- **WHEN** 新任务的详细程度为 `concise`
- **THEN** 提示词 MUST 要求只保留结论、核心概念、关键数据和必要步骤，并主动压缩重复解释和次要示例

#### Scenario: 适中档为默认

- **WHEN** 用户从未修改详细程度
- **THEN** 新任务 MUST 使用 `balanced`，提示词 SHALL 保留主要论点、必要解释、代表性示例和结论

#### Scenario: 详细与超详细逐级增加覆盖

- **WHEN** 相同输入分别使用 `detailed` 与 `exhaustive`
- **THEN** 两者提示词 MUST 分别要求补充上下文、推导、例子和注意事项，以及尽量完整的推导链、反例、边界和术语说明；`exhaustive` 的覆盖要求 MUST 严格高于 `detailed`

#### Scenario: PDF 分支同样应用详细程度

- **WHEN** 任务携带 PDF 参考材料且详细程度为 `exhaustive`
- **THEN** `generate_with_pdf_reference` 提示词 MUST 同时包含讲义对照规则和超详细约束，MUST NOT 因进入 PDF 分支丢失档位

#### Scenario: 重跑沿用任务快照

- **WHEN** 任务以 `concise` 创建后，全局设置改为 `exhaustive`，用户重跑原任务
- **THEN** 重跑 MUST 继续使用原任务的 `concise` 快照，新建任务才使用 `exhaustive`
