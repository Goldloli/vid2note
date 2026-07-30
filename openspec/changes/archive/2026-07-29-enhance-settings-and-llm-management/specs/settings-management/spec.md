## ADDED Requirements

### Requirement: 非敏感设置独立文件持久化

系统 MUST 将用户在设置页保存的非敏感配置以 JSON 写入 `${DATA_ROOT}/config/settings.json`，该文件 SHALL 位于 compose 的 `./data` bind mount 中并作为运行时设置权威态。写入 MUST 使用临时文件加原子替换，容器重建后 MUST 保留；文件损坏时 MUST 报告明确错误并回落到合法默认值，MUST NOT 静默覆盖损坏文件。

#### Scenario: 保存设置后独立文件可读

- **WHEN** 用户修改输出语言和并发数并保存
- **THEN** `${DATA_ROOT}/config/settings.json` MUST 包含新值，SQLite 任务记录 MUST 不受影响，重建容器后读取值 MUST 与保存值一致

#### Scenario: 原子写入避免半文件

- **WHEN** 设置保存过程中进程在原子替换前异常退出
- **THEN** 原 `settings.json` MUST 保持完整可读，MUST NOT 留下一份被当作权威态的半截 JSON

#### Scenario: 损坏文件不被静默覆盖

- **WHEN** `settings.json` 存在但不是合法 JSON
- **THEN** 后端 MUST 记录并返回配置不可用状态、运行时回落合法默认值，MUST NOT 自动覆盖原损坏文件

### Requirement: 九种 LLM 配置槽位

系统 MUST 同时维护 DeepSeek、Qwen、GLM、Moonshot/Kimi、百度千帆、豆包、MiniMax、Ollama 和一个 `custom` OpenAI-compatible 槽位。每个槽位 MUST 独立保存显示名、模型 ID、Base URL 与所需凭证；任一时刻 MUST 有且仅有一个默认 provider。内置槽位 MUST 提供受维护的默认模型和 Base URL，模型 ID MUST 可由用户自由编辑且保存后不得被自动覆盖。

#### Scenario: 各 provider 配置互不覆盖

- **WHEN** 用户分别保存 DeepSeek 与 Qwen 的模型、URL 和密钥，再在二者间切换
- **THEN** 两组配置 MUST 各自保留，切换默认 provider MUST NOT 清空或覆盖另一组配置

#### Scenario: 内置 provider 提供当前默认模型

- **WHEN** 首次启动且没有已有配置
- **THEN** DeepSeek / Qwen / GLM / Kimi / 百度 / 豆包 / MiniMax / Ollama 的模型 MUST 分别默认为 `deepseek-v4-flash` / `qwen3.7-plus` / `glm-5.2` / `kimi-k2.6` / `ernie-5.0` / `doubao-seed-2-0-lite-260215` / `MiniMax-M2.7` / `qwen3.5`

#### Scenario: 用户可填写任意模型 ID

- **WHEN** 用户把某内置 provider 的模型框改成该服务支持的其他非空模型 ID 并保存
- **THEN** 后端 MUST 保存并在后续任务使用该精确值，MUST NOT 因其不等于内置建议值而拒绝或改写

#### Scenario: 自定义 OpenAI 兼容槽位

- **WHEN** 用户配置 `custom` 的名称、Base URL、模型 ID 和可选 API Key
- **THEN** 后续选择该 provider 的任务 MUST 通过用户填写的 OpenAI Chat Completions 兼容地址和模型调用

### Requirement: 凭证加密、状态与按需查看

LLM API Key、外部 ASR API Key 和 Bilibili cookie MUST 使用认证加密写入 `${DATA_ROOT}/config/credentials.enc`，MUST NOT 出现在 `settings.json`、普通设置响应或日志中。主密钥 MUST 优先从 `VID2NOTE_MASTER_KEY` 或 Docker secret 文件读取；两者均无时 SHALL 生成权限为 `0600` 的 `${DATA_ROOT}/config/master.key`。普通设置响应 MUST 按字段返回 `configured`、掩码和尾号；只有显式 reveal 请求可返回一个白名单字段的明文。

#### Scenario: 普通读取只返回状态和掩码

- **WHEN** DeepSeek API Key 已配置且前端加载设置页
- **THEN** 普通设置响应 MUST 表明该字段已配置并返回类似 `••••••••a1b2` 的掩码，MUST NOT 包含完整密钥

#### Scenario: 点击眼睛后按需读取明文

- **WHEN** 用户点击已配置 API Key 输入框右侧的眼睛按钮
- **THEN** 前端 MUST 调用独立 reveal 接口读取该 provider 的该字段，输入框 SHALL 临时显示明文，响应 MUST 设置 `Cache-Control: no-store`

#### Scenario: 明文自动清除

- **WHEN** 密钥已显示且用户关闭眼睛、切换 provider/页签或经过 60 秒
- **THEN** 前端 MUST 从编辑状态清除已读取明文并恢复黑点显示

#### Scenario: 空输入不覆盖已有密钥

- **WHEN** 某密钥已配置，用户编辑其他字段但未输入新密钥并保存
- **THEN** 已有密钥 MUST 保持不变；只有显式点击清除并确认时才能删除该凭证

#### Scenario: 密文被篡改

- **WHEN** `credentials.enc` 内容被修改而无法通过完整性校验
- **THEN** 后端 MUST 拒绝解密并报告凭证存储损坏，MUST NOT 返回猜测值、空值冒充成功或把异常内容写入日志

### Requirement: LLM 连接测试

每个 LLM 槽位 MUST 支持用户主动触发的连接测试。测试 MUST 使用当前已保存或正在提交的 provider、Base URL、模型与凭证发送最小生成请求，并返回成功状态、耗时和不含敏感信息的错误摘要。系统 MUST NOT 在页面加载时自动发起测试。

#### Scenario: 配置正确时测试成功

- **WHEN** 用户为某 provider 保存有效 URL、模型和密钥并点击「测试连接」
- **THEN** 后端 MUST 发起最小模型请求，前端 MUST 显示成功与耗时

#### Scenario: 密钥错误时不泄漏凭证

- **WHEN** provider 返回鉴权失败
- **THEN** 前端 MUST 显示可理解的鉴权失败信息，响应、日志和错误文本 MUST NOT 包含提交的密钥

#### Scenario: 测试只由用户主动触发

- **WHEN** 用户打开或刷新 LLM 设置页但未点击测试
- **THEN** 系统 MUST NOT 向任何 LLM 服务发送网络请求或产生模型费用

### Requirement: SQLite 设置一次性迁移

升级后首次启动且外置配置不存在时，系统 MUST 把 SQLite 中的旧设置拆分迁移到 `settings.json` 和 `credentials.enc`。迁移 MUST 在写入、重新读取和解密验证全部成功后才标记完成并清除 SQLite 中的敏感值；失败时 MUST 保留旧值并继续使用旧设置路径。

#### Scenario: 旧设置成功迁移

- **WHEN** 旧 SQLite 含默认 provider、模型和多个 provider 凭证，且外置配置尚不存在
- **THEN** 新设置文件 MUST 保存非敏感值、加密文件 MUST 可解出原凭证、迁移标记 MUST 写入，SQLite 中旧敏感值 MUST 被清除

#### Scenario: 迁移写入失败

- **WHEN** 配置目录不可写或密钥生成失败
- **THEN** 启动 MUST 保留并使用 SQLite 旧设置，MUST NOT 删除任何旧配置，并 MUST 暴露明确的迁移失败诊断
