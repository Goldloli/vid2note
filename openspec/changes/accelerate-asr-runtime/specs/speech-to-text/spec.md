## ADDED Requirements

### Requirement: bcut 限流单飞探测与共享冷却

当长音频在在线优先策略下选择 bcut 时，系统 MUST 先以一个真实分段完成串行可用性探测，探测成功后才 SHALL 并发处理剩余在线分段。当任一探测或在线分段收到 HTTP 412/429 时，系统 MUST 在任务内停用 bcut、记录一次降级，并将限流冷却共享给同进程及后续任务；冷却有效期内新任务 MUST 跳过 bcut 并直接使用允许的后备引擎。

#### Scenario: 远端正常时首段成功后并发

- **WHEN** 长音频被切分为多个在线分段且 bcut 首段探测成功
- **THEN** 首段结果 MUST 纳入最终 SRT，剩余分段 SHALL 按在线并发配置处理

#### Scenario: 首段限流时剩余分段不再撞接口

- **WHEN** bcut 首段探测返回 HTTP 412 或 429，策略为在线优先
- **THEN** 当前任务 MUST 只记录一次 bcut 到 Whisper 的降级，剩余分段 MUST 跳过 bcut 并由本地引擎完成

#### Scenario: 多任务共享远端冷却

- **WHEN** 一个任务已确认 bcut 处于 412/429 限流冷却，另一个任务随后开始 ASR
- **THEN** 后续任务 MUST 在发起在线请求前发现冷却，并 MUST NOT 再调用 bcut

#### Scenario: 冷却过期后恢复探测

- **WHEN** 共享限流冷却已经超过配置的滚动窗口
- **THEN** 新任务 SHALL 重新执行一次 bcut 首段探测，而不是永久停用在线引擎

### Requirement: 本地 CPU Whisper 跨任务容量调度

在单进程运行时，系统 MUST 将本地 CPU Whisper 作为容量为 1 的共享资源。一个任务首次降级或选择本地 Whisper 后 MUST 获取任务级执行槽，并在该任务的全部本地分段完成、取消或失败后释放；不同任务的本地 Whisper 推理 MUST NOT 同时运行。在线 bcut 分段 MUST NOT 受本地执行槽限制。

#### Scenario: 两个本地长任务不同时推理

- **WHEN** 两个任务同时进入本地 Whisper 长音频转写
- **THEN** 最多一个任务 SHALL 执行本地推理，另一个任务 MUST 等待前一个任务释放执行槽

#### Scenario: 在线任务保持并发

- **WHEN** 多个任务的 bcut 探测均成功且无需本地降级
- **THEN** 这些任务 SHALL 继续按在线并发配置工作，MUST NOT 因本地执行槽而串行化

#### Scenario: 等待本地槽时可以取消

- **WHEN** 任务正在等待本地执行槽且收到取消请求
- **THEN** 等待 MUST 及时终止并以取消状态退出，MUST NOT 泄漏或错误释放其他任务持有的槽

#### Scenario: 异常后释放本地槽

- **WHEN** 持有本地执行槽的任务在 Whisper 推理或分段拼接期间抛出异常
- **THEN** 系统 MUST 在清理路径释放执行槽，使后续任务能够继续

### Requirement: ASR 运行时协调指标

系统 SHALL 在 ASR 节点 metadata 中记录在线探测、共享冷却跳过和本地槽等待情况，且 MUST 保持既有引擎尝试、成功分段、降级次数与耗时字段兼容。

#### Scenario: 本地等待时间可观测

- **WHEN** 一个任务因其他任务占用本地执行槽而等待
- **THEN** ASR metadata MUST 包含非负的本地槽等待秒数和已取得执行槽标志

#### Scenario: 冷却跳过可观测

- **WHEN** 任务因共享 bcut 冷却直接使用本地引擎
- **THEN** ASR metadata MUST 标记本任务未发起在线探测并因冷却跳过 bcut
