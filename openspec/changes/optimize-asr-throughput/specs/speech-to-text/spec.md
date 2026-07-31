## MODIFIED Requirements

### Requirement: 长音频 VAD 分段并行转录

对于超过单次转写阈值的音频，该 capability SHALL 使用 VAD（语音活性检测）按静音切分为多段，对各段并行调用 ASR 引擎转录（在线 bcut 与本地 whisper.cpp 均分段——实测 bcut 整段上限约 6 分钟，长音频整段必失败，MUST NOT 对长音频整段尝试），再按每段相对音频起始的时间偏移量将该段字幕时间戳叠加偏移后拼回，产出一份时间戳连续且单调递增的完整 SRT。分段并行度由 `concurrency`（默认 2）控制。分段与拼合对调用方 MUST 透明（调用方只看到一份完整的 SRT）。

#### Scenario: 短音频不触发分段

- **WHEN** 输入音频时长小于单次转写阈值（如 5 分钟）
- **THEN** 该 capability MUST 直接将整段音频送入 ASR 引擎，MUST NOT 进行 VAD 分段，产出单份 SRT

#### Scenario: 长音频按静音分段并行转录

- **WHEN** 输入音频时长超过单次转写阈值（无论在线或本地引擎），且 VAD 在静音处成功切分出多段
- **THEN** 该 capability MUST 对各段并行调用 ASR 引擎（并行度由 `concurrency` 控制），最终拼合为一份 SRT

#### Scenario: 分段时间戳按偏移拼回

- **WHEN** 一个从音频第 300 秒开始、第 360 秒结束的片段被单独转录，该片段内 ASR 产出的某条字幕相对片段起始为 10 秒
- **THEN** 拼合后的 SRT 中该条字幕的起始时间戳 MUST 为 00:05:10（即 310 秒，偏移叠加后），整份 SRT 时间戳连续、无错位

#### Scenario: 拼合后 SRT 连续单调

- **WHEN** 长音频完成分段转录并按偏移拼合
- **THEN** 最终 SRT 中相邻字幕的时间戳 MUST 单调递增、不存在时间回退，跨段拼接处不存在时间戳重叠或空洞

### Requirement: 在线引擎降级与日志记录

当在线 ASR 引擎（`bcut` 或外部 endpoint）出现服务不可用、超时、限流（HTTP 429）、协议变化或鉴权失败等情形时，该 capability SHALL 对瞬时错误（HTTP 429/5xx）**先经有限次自动重试（带退避）**，重试用尽仍失败才降级到可用的备选引擎（在「在线优先」策略下降级到本地 whisper.cpp）。每一次降级事件 MUST 在日志中记录，日志内容 SHALL 包含触发降级的原因（失败类型或 HTTP 状态码）、原引擎、降级目标引擎与时间戳。

#### Scenario: 瞬时错误重试成功不降级

- **WHEN** 在线 `bcut` 引擎首次返回限流（HTTP 429）或 5xx，但有限重试内某次成功
- **THEN** 该 capability MUST 返回该次成功结果，MUST NOT 触发降级，MUST NOT 在日志中记录降级事件

#### Scenario: 在线引擎限流重试用尽后降级并记录

- **WHEN** 在线 `bcut` 引擎在有限重试内持续返回限流（HTTP 429）或服务端错误，且引擎策略为「在线优先，失败转本地」
- **THEN** 该 capability MUST 自动降级到本地 whisper.cpp 完成转写，且 MUST 在日志中记录一条降级事件，事件中包含触发原因（429/限流）、原引擎（`bcut`）、目标引擎（whisper.cpp）

#### Scenario: 在线引擎超时时降级并记录

- **WHEN** 在线引擎在配置的超时时间内未返回结果（网络超时），且引擎策略为「在线优先，失败转本地」
- **THEN** 该 capability MUST 中止该次在线调用并降级到本地引擎完成转写，且 MUST 在日志中记录一次超时降级事件

#### Scenario: 所有引擎均不可用时报错

- **WHEN** 在线引擎重试用尽后失败，且本地 whisper.cpp 同样不可用（如模型文件缺失），已无可用引擎
- **THEN** 该 capability MUST 抛出明确的「无可用 ASR 引擎」错误并终止，MUST NOT 返回部分 SRT，且终止前 SHALL 在日志中记录已尝试的引擎与各自失败原因

### Requirement: ASR 引擎参数可配置与校验

独立 ASR 页面 SHALL 允许配置现有 `AsrConfig` 实际消费的参数：bcut 超时、**bcut 轮询起步间隔与最大等待**；Whisper 模型路径、可选 binary 与识别语言；外部 ASR endpoint、API Key 与超时；VAD 触发阈值、目标分段时长、分段并发和请求超时；**ASR 结果缓存开关**。后端 MUST 对 URL、数值范围和枚举做白名单校验，非法请求 MUST 整体拒绝且不得部分写入。`whisper_device=cpu` 与 `whisper_compute_type=int8` SHALL 作为当前实现约束展示，MUST NOT 伪装成可用的 GPU 选项。

#### Scenario: Whisper 配置用于引擎构造

- **WHEN** 用户保存模型路径、binary 和识别语言后选择 Whisper 本地
- **THEN** 后续任务构造 `WhisperCppEngine` 时 MUST 使用这些值，且仍 MUST 使用 CPU / int8

#### Scenario: 外部 ASR 凭证从加密存储解析

- **WHEN** 用户保存外部 endpoint、API Key 和超时后创建外部 ASR 任务
- **THEN** endpoint 与超时 MUST 来自非敏感设置，API Key MUST 在运行时从加密凭证存储解析并用于 Authorization，普通设置响应 MUST NOT 返回明文

#### Scenario: VAD 数值非法时整体拒绝

- **WHEN** 用户把 VAD 阈值设为负数或把分段并发设为 0
- **THEN** 后端 MUST 返回校验错误，原 ASR 配置 MUST 保持完整不变

#### Scenario: bcut 轮询参数与缓存开关可配

- **WHEN** 用户保存 bcut 轮询起步间隔、最大等待与缓存开关
- **THEN** 后续 `BcutEngine` 构造 MUST 采用这些值（轮询按指数退避、缓存按开关启停），非法数值（如负间隔）MUST 被整体拒绝

## ADDED Requirements

### Requirement: ASR 结果文件级缓存

该 capability SHALL 对 ASR 结果提供文件级缓存：以音频字节内容的 crc32 为键，同一份音频（字节级相同）在同一引擎与语言下命中缓存时 MUST 直接返回缓存的转录结果，跳过上传与轮询。缓存键 MUST 包含引擎名、音频字节 crc32 与识别语言，内容不同的音频 MUST NOT 命中。缓存命中对调用方透明（返回结果等价于实际转录）。缓存 SHALL 可通过设置开关关闭；关闭时 MUST 正常执行上传与轮询、MUST NOT 读写缓存。

#### Scenario: 同音频命中缓存跳过上传

- **WHEN** 一份音频已被某引擎以某语言转录过且缓存开启，再次以相同引擎与语言转录同一份（字节级相同）音频
- **THEN** 该 capability MUST 直接返回缓存结果，MUST NOT 再次上传音频或轮询在线服务

#### Scenario: 不同音频不命中缓存

- **WHEN** 两份内容不同（crc32 不同）的音频以相同引擎与语言转录
- **THEN** 各自 MUST 独立执行上传与轮询，MUST NOT 错误地复用对方的缓存结果

#### Scenario: 缓存关闭时正常转录

- **WHEN** 缓存开关被关闭，对任意音频转录
- **THEN** 该 capability MUST 正常上传与轮询，MUST NOT 读写缓存文件
