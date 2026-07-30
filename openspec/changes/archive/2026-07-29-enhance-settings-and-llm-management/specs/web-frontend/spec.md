## MODIFIED Requirements

### Requirement: 设置页 ASR 与 LLM 引擎配置

设置中心 MUST 采用「通用 / LLM 服务 / 笔记生成 / 存储与清理 / 高级设置 / 关于」六个页签。设置中心 MUST NOT 再提供第二套完整 ASR 表单，只 SHALL 展示当前 ASR 摘要与进入独立 ASR 页的入口。LLM 页签 MUST 展示八家内置 provider 和一个自定义 OpenAI-compatible 槽位，允许分别编辑模型、Base URL 和所需凭证，并有且仅有一个默认 provider。已配置凭证输入框 MUST 默认显示黑点和配置状态，右侧 MUST 提供可访问的眼睛按钮按需切换明文。

#### Scenario: 六个设置页签切换

- **WHEN** 用户打开设置中心并依次点击六个页签
- **THEN** 页面 MUST 只展示当前页签内容，切换 MUST NOT 丢失尚未保存的同页编辑状态，窄屏下页签 MUST 可横向滚动或换行且不得溢出

#### Scenario: 设置页只显示 ASR 摘要

- **WHEN** 用户在设置中心查看通用或相关摘要区域
- **THEN** 页面 SHALL 显示当前默认 ASR 和策略，并提供「前往 ASR 设置」，MUST NOT 出现可与独立 ASR 页产生冲突的第二套完整编辑表单

#### Scenario: 九种 LLM 槽位各可配置

- **WHEN** 用户进入 LLM 服务页签
- **THEN** 页面 MUST 列出 DeepSeek、Qwen、GLM、Kimi、百度千帆、豆包、MiniMax、Ollama 和自定义槽位，并展示默认/已配置/未配置/本地等状态

#### Scenario: 模型有建议值且允许自由填写

- **WHEN** 用户选择任一内置 provider
- **THEN** 模型输入框 MUST 初始显示该 provider 的建议模型 ID，并允许用户直接编辑成其他非空 ID

#### Scenario: 已配置密钥默认显示黑点

- **WHEN** 某 provider 的 API Key 已保存并重新加载页面
- **THEN** 输入框 MUST 显示黑点而非空白，旁边 MUST 显示「已配置」和安全尾号，使用户可区分未配置状态

#### Scenario: 眼睛按钮查看与隐藏明文

- **WHEN** 用户点击密钥框右侧眼睛按钮
- **THEN** 页面 MUST 按需读取并显示明文；再次点击、切换 provider/页签或超时后 MUST 恢复黑点并清除明文

#### Scenario: LLM 默认提供商为 DeepSeek

- **WHEN** 首次启动且没有任何 LLM 配置
- **THEN** 默认 provider MUST 为 DeepSeek、模型 MUST 为 `deepseek-v4-flash`，主控台新建任务的 LLM 默认项 MUST 与之一致

#### Scenario: Ollama 与自定义地址可配置

- **WHEN** 用户选择 Ollama 或自定义槽位
- **THEN** 页面 MUST 允许填写容器可达的 Base URL；Ollama SHALL 提示 API Key 非必需，自定义槽位 MUST 要求非空名称、模型和 URL

### Requirement: 设置页处理选项

设置中心 MUST 在对应页签提供界面语言、背景、输出语言、四档笔记详细程度、图片提取与质量、PDF 模式、并发任务数（1~3）、分块大小、Temperature、最大重试次数和五类保留策略。截图嵌入 SHALL 继续作为新建任务的逐任务选项，但设置页可提供新任务默认值。PDF 只展示当前稳定的 `pypdf`，MUST NOT 展示未实现的 MinerU 选择。

#### Scenario: 笔记详细程度四档可选

- **WHEN** 用户在笔记生成页签选择「简洁 / 适中 / 详细 / 超详细」之一并保存
- **THEN** `note.detail_level` MUST 保存为对应合法值，页面 MUST 解释该档位对覆盖率和 token/耗时的影响，后续新建任务 MUST 使用该默认档位

#### Scenario: 截图嵌入逐任务选择

- **WHEN** 用户在主控台创建任务
- **THEN** 截图开关 MUST 以设置默认值预填且仍可为本次任务覆盖，本次选择 SHALL 只影响本任务

#### Scenario: 并发任务数限定 1~3 且越界被拒

- **WHEN** 用户尝试将并发任务数设为 0 或 4（或范围外任意值）并保存
- **THEN** 前端 MUST 校验失败并阻止保存；合法值 MUST 保存成功

#### Scenario: 高级数值显示范围与说明

- **WHEN** 用户打开高级设置
- **THEN** chunk size、Temperature 和最大重试次数 MUST 以带最小值/最大值/用途说明的数字字段展示，非法值 MUST 在提交前提示

#### Scenario: 保存反馈不使用阻塞弹窗

- **WHEN** 用户保存任一页签
- **THEN** 页面 MUST 以页内状态或 toast 展示保存中、成功或错误，MUST NOT 使用浏览器原生 `alert`

### Requirement: ASR 管理页

系统 MUST 保留一个经侧栏到达的独立 ASR 管理页，并采用「引擎 / Whisper 本地 / 外部 ASR / 转录策略」四个内部页签。页面 MUST 集中承载三种引擎的说明、默认选择、配置和诊断。实验性在线 ASR 的用户可见名称 MUST 为「bcut」，不得暗示官方、稳定或保证免费，也不得暴露内部兼容实现名。

#### Scenario: 四个 ASR 页签职责清晰

- **WHEN** 用户依次切换四个 ASR 页签
- **THEN** 引擎页 MUST 展示三引擎卡片与总览，Whisper 页 MUST 展示本地模型参数，外部页 MUST 展示 endpoint/凭证，策略页 MUST 展示降级/VAD/并发参数

#### Scenario: 三引擎说明可见

- **WHEN** 用户打开 ASR 的引擎页签
- **THEN** 页面 MUST 展示 bcut（在线、实验性、无需本地 GPU）、Whisper 本地（离线、CPU）与外部 ASR（自建 HTTP）三张卡片，每张 MUST 含适用场景、当前状态和测试入口

#### Scenario: 默认引擎与策略持久化

- **WHEN** 用户选择默认引擎为 bcut、策略为在线优先并保存
- **THEN** `asr.engine` / `asr.strategy` MUST 持久化，刷新或重启后保留，主控台默认引擎 MUST 同步

#### Scenario: Whisper 参数可配置

- **WHEN** 用户填写模型路径、可选 binary 和识别语言并保存
- **THEN** 配置 MUST 在 Whisper 页重新加载时完整显示，状态区 MUST 基于后端检查展示模型和 binary 是否就绪

#### Scenario: 外部 endpoint 和密钥可配置

- **WHEN** 用户填写外部 ASR endpoint、API Key 与超时并保存
- **THEN** endpoint 与超时 MUST 写入非敏感设置，API Key MUST 进入加密凭证存储；重新加载时密钥框 MUST 显示已配置黑点

#### Scenario: 连通性测试反馈结果

- **WHEN** 用户对某个引擎点击「测试连接」
- **THEN** 前端 MUST 调用后端测试接口并反馈成功耗时或失败原因，MUST NOT 在未测试时声称连接可用

#### Scenario: 页面响应式可用

- **WHEN** 页面宽度缩小到手机尺寸
- **THEN** 页签、引擎卡片、表单与操作按钮 MUST 重排为单列或可滚动布局，MUST NOT 出现水平页面溢出或被遮挡的保存按钮
