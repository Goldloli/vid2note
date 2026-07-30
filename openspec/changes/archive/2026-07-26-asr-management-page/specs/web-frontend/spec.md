## ADDED Requirements

### Requirement: ASR 管理页

系统 MUST 提供一个独立的「ASR」管理页（通过侧栏导航可达），集中承载 ASR 引擎的全部配置与诊断：三种引擎的说明与适用场景、默认引擎与引擎策略选择、外部 endpoint 配置、各引擎就绪态、以及连通性测试。实验性在线 ASR 在用户可见文案中 MUST 对外称作「bcut」，不得暗示其为官方、稳定或保证免费的公共服务。

#### Scenario: 三引擎说明可见

- **WHEN** 用户打开 ASR 管理页
- **THEN** 页面 MUST 展示三张引擎卡片：bcut（在线·实验性）/ Whisper 本地（离线·CPU）/ 外部 ASR（自建 HTTP），每张 MUST 含一句适用场景说明

#### Scenario: 默认引擎与策略选择并持久化

- **WHEN** 用户在 ASR 页选择默认引擎为「bcut」并将策略切到「在线优先·失败转本地」，保存
- **THEN** 该选择 MUST 持久化到后端（`asr.engine` / `asr.strategy`），刷新或重启后保留，且主控台新建任务的默认引擎 MUST 同步

#### Scenario: 外部 endpoint 可配置

- **WHEN** 用户在 ASR 页填写外部 ASR 的 HTTP endpoint 与 API Key 并保存
- **THEN** 该配置 MUST 持久化到 `asr.config`，后续选择「外部 ASR」引擎或在线优先降级时 MUST 能取到该 endpoint

#### Scenario: 各引擎就绪态展示

- **WHEN** 用户打开 ASR 页
- **THEN** 页面 MUST 展示各引擎就绪态：bcut 的 provider、Whisper 本地的模型文件 / binary 是否就绪、外部 ASR 是否已配置 endpoint；数据 MUST 来自后端 `GET /asr/status` 而非前端臆测

#### Scenario: 连通性测试反馈结果

- **WHEN** 用户对某个引擎点击「测试连通性」
- **THEN** 前端 MUST 调用后端 `POST /asr/test` 对该引擎做探活 / 模型可加载检查，并 MUST 反馈结果（成功时含耗时，失败时含原因），MUST NOT 在未测试时声称可用

## MODIFIED Requirements

### Requirement: 应用骨架与六页导航

前端 MUST 以浏览器访问 `localhost:8765` 的 Web 应用形态提供（由 FastAPI 后端直接托管静态资源，MUST NOT 依赖 Electron 客户端），并 MUST 包含与高保真原型对齐的统一应用骨架：顶部标题栏、左侧固定侧栏、右侧主内容区。侧栏 MUST 提供七个导航入口 —— 主控台 / 任务详情 / 笔记 / 思维导图 / 历史 / ASR / 设置，且当前所在页 MUST 在侧栏中被高亮为激活态。侧栏底部 MUST 始终展示一份引擎状态卡，实时反映当前选定的 ASR 引擎、LLM 引擎与后端运行态。

#### Scenario: 六页均可通过侧栏到达且布局对齐原型

- **WHEN** 用户在浏览器中打开 `localhost:8765` 并依次点击侧栏的导航项
- **THEN** 应用 MUST 分别渲染主控台、任务详情、笔记、思维导图、历史、ASR、设置各页面，每页的主结构（标题栏 + 侧栏 + 主内容区）MUST 与原型布局一致

#### Scenario: 当前页在侧栏高亮

- **WHEN** 用户处于任一页面（例如「ASR」）
- **THEN** 侧栏中该导航项 MUST 被标记为激活态（与其他项有可区分的视觉样式），且其余项 MUST NOT 同时处于激活态

#### Scenario: 侧栏引擎状态卡反映当前配置与后端运行态

- **WHEN** 用户在 ASR / 设置页切换了默认 ASR 或 LLM 引擎，或后端运行态发生变化
- **THEN** 侧栏底部引擎状态卡 MUST 显示最新的 ASR 引擎名、LLM 引擎名与后端运行态（运行中 / 异常），MUST NOT 显示过期值

#### Scenario: 前端为浏览器 Web 应用而非 Electron

- **WHEN** 用户在设置「关于」区域查看运行模式
- **THEN** 页面 MUST 显示其为 Docker 部署的 Web 应用（服务地址 `http://localhost:8765`），MUST NOT 出现「electron」「桌面客户端」等与 v1 形态不符的标识

### Requirement: 设置页 ASR 与 LLM 引擎配置

设置页 MUST 提供 ASR 引擎选择（含在线 / 本地 / 外部三种可选引擎）与连通性测试入口；ASR 引擎选择 MUST 持久化到后端 `asr.engine`（修复 v1 早期 key 名不匹配导致存不进的问题）；MUST 提供引擎策略选择（在线优先·失败转本地 / 指定单一）；MUST 提供八家 LLM 提供商（通义千问 Qwen、DeepSeek、智谱 GLM、Moonshot/Kimi、百度文心、字节豆包 Doubao、MiniMax、Ollama 本地）的配置，每家 MUST 可填写其所需的凭证（API Key / Secret Key / Group ID / Host 之一或多项）、模型与 Base URL，并 MUST 提供连接测试。默认 LLM 提供商 MUST 为 DeepSeek（模型 `deepseek-v4-flash`）；默认在线 ASR provider MUST 为 `bcut`。

#### Scenario: ASR 引擎可选且持久化

- **WHEN** 用户在设置页的 ASR 区域选择某一 ASR 引擎（bcut / Whisper 本地 / 外部 ASR 三者之一）并保存
- **THEN** 该选择 MUST 被持久化到 `asr.engine`，刷新或重启容器后 MUST 仍为该值，且主控台新建任务的 ASR 默认选中项 MUST 同步更新

#### Scenario: ASR 引擎策略可选

- **WHEN** 用户选择策略为「在线优先·失败转本地」或「指定单一」并保存
- **THEN** 该策略 MUST 持久化到 `asr.strategy`，后续任务 MUST 按所选策略执行（在线优先在失败时降级本地；指定单一下不降级）

#### Scenario: ASR 云端 Key 可填写并测试连通性

- **WHEN** 用户填写 ASR 云端相关配置并点击「测试」（或跳转 ASR 管理页测试）
- **THEN** 前端 MUST 调用后端进行连通性测试并反馈结果（成功 / 失败及原因），成功时 MUST 展示「验证通过」状态

#### Scenario: 八家 LLM 提供商各可配置

- **WHEN** 用户进入设置页的 LLM 区域
- **THEN** 页面 MUST 列出八家 LLM 提供商（Qwen / DeepSeek / GLM / Moonshot / 百度文心 / Doubao / MiniMax / Ollama），每家 MUST 可展开填写其所需凭证字段、模型与 Base URL，且 MUST 有且仅有一家处于选中态（单选）

#### Scenario: LLM 默认提供商为 DeepSeek

- **WHEN** 首次启动且数据库无任何 LLM 配置
- **THEN** 选中的默认 LLM 提供商 MUST 为 DeepSeek，默认模型 MUST 为 `deepseek-v4-flash`，主控台新建任务的 LLM 默认选中项 MUST 与之一致

#### Scenario: LLM 连接测试反馈结果

- **WHEN** 用户为某家 LLM 填写凭证后点击「测试连接」
- **THEN** 前端 MUST 调用后端对该配置发起测试调用，并 MUST 向用户反馈结果（成功时可展示延迟，失败时展示原因），MUST NOT 在未测试的情况下声称连接正常
