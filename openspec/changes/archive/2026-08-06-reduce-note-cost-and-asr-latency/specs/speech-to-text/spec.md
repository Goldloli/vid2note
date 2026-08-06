## MODIFIED Requirements

### Requirement: 长音频 VAD 分段并行转录

对于超过单次转写阈值的音频，该 capability SHALL 使用 VAD 按静音切分为多段并按引擎选择并发和临时格式。bcut 在线路径 MUST 默认使用 280 秒目标分段、295 秒硬上限、3 个有界 worker 和 16 kHz 单声道 64 kbps MP3；本地 Whisper 路径 MUST 默认单 worker 并可使用无损 WAV。各段字幕按起始偏移拼回，最终 SRT 时间戳 MUST 连续且单调递增。分段与拼合对调用方 MUST 透明。

#### Scenario: 短音频不触发分段
- **WHEN** 输入音频时长小于单次转写阈值
- **THEN** 该 capability MUST 直接将整段音频送入 ASR 引擎，MUST NOT 进行 VAD 分段

#### Scenario: bcut 长音频使用在线档案
- **WHEN** 约 150 分钟音频由 bcut 在线转录且使用默认配置
- **THEN** 系统 MUST 以约 280 秒为目标在静音处切分，默认最多同时执行 3 个在线段任务，上传临时文件 MUST 为语音 MP3 而非 PCM WAV

#### Scenario: 本地 Whisper 保持单并发
- **WHEN** bcut 降级到本地 Whisper 或任务指定本地引擎
- **THEN** 本地转录 MUST 使用单 worker 和本地适用的音频格式，MUST NOT 因在线并发配置同时运行多个 CPU 模型调用

#### Scenario: 分段时间戳按偏移拼回
- **WHEN** 一个从音频第 300 秒开始的片段产出相对起始 10 秒的字幕
- **THEN** 拼合后的字幕起始时间 MUST 为 310 秒，整份 SRT MUST 无时间回退或跨段重叠

### Requirement: ASR 引擎参数可配置与校验

独立 ASR 页面 SHALL 允许配置 bcut 超时、在线目标分段、在线并发、缓存开关、在线临时格式；Whisper 模型路径、语言和本地并发；外部 endpoint、凭证与超时。后端 MUST 对 URL、数值范围、格式枚举和并发范围做白名单校验，非法请求 MUST 整体拒绝。旧 `concurrency` MUST 只作为兼容输入，新设置 MUST 使用 `online_concurrency` 与 `local_concurrency`。

#### Scenario: 在线与本地并发分别生效
- **WHEN** 配置在线并发 3、本地并发 1
- **THEN** bcut 分段线程池 MUST 使用最多 3 个 worker，Whisper MUST 使用 1 个 worker，全局任务并发 MUST NOT 覆盖二者

#### Scenario: 旧并发配置迁移
- **WHEN** 旧设置只含 `concurrency`
- **THEN** 后端 MUST 安全读取该值并在下一次保存时写入新字段，状态端点 MUST 展示实际生效的在线与本地并发

#### Scenario: 非法格式整体拒绝
- **WHEN** 用户提交不支持的在线临时格式或越界并发
- **THEN** 后端 MUST 返回校验错误且原 ASR 配置完整不变

## ADDED Requirements

### Requirement: VAD 前整段音频内容缓存

系统 MUST 在 VAD 检测之前查询整段音频缓存。缓存键 MUST 使用强内容哈希并包含引擎、语言、缓存 schema 版本及影响识别结果的配置；缓存值 MUST 原子写入数据卷。命中时 MUST 跳过 VAD、切片、上传和轮询，损坏时 MUST 忽略并执行冷启动。

#### Scenario: 完全相同音频热命中
- **WHEN** 同一音频和相同识别配置第二次执行
- **THEN** 系统 MUST 直接从整段缓存恢复 Cue 并生成 SRT，MUST NOT 创建任何 bcut 上传任务

#### Scenario: 配置变化不误命中
- **WHEN** 音频相同但引擎、语言或影响结果的缓存版本不同
- **THEN** 缓存键 MUST 不同，系统 MUST 冷启动转录

#### Scenario: 缓存文件损坏
- **WHEN** 匹配键的缓存 JSON 无法完整解析
- **THEN** 系统 MUST 忽略该项并重新转录，MUST NOT 返回部分或伪造字幕

### Requirement: bcut 连接轮询与重试控制

bcut 每个 worker MUST 复用线程内 HTTP Session；轮询 SHALL 快速起步且最大间隔不超过 4 秒。自动 HTTP 重试 MUST 限于幂等或可安全重放的请求，创建任务 POST MUST NOT 被底层自动重复；外层完整任务重试 MUST 有严格上限，412/429 MUST NOT 被立即重试。

#### Scenario: 同一 worker 处理多段
- **WHEN** 一个 worker 顺序处理多个分段
- **THEN** 多个分段的 HTTP 客户端 MUST 复用该 worker 的连接池，同时每段任务 ID 与上传状态 MUST 相互隔离

#### Scenario: 创建任务失败不被隐式重复
- **WHEN** 创建任务 POST 的响应不确定
- **THEN** urllib3 自动重试 MUST NOT 再次发送该 POST，系统 MUST 以结构化错误进入受控外层重试或降级

#### Scenario: 远端限流触发本任务熔断
- **WHEN** 任一 bcut worker 收到 HTTP 412 或 429
- **THEN** 系统 MUST 停止本任务后续分段继续尝试 bcut，MUST NOT 立即重试同一远端任务

### Requirement: bcut 滚动公益额度整项预检

系统 MUST 在整项冷启动任务开始前，以持久化滚动窗口预留预计 bcut 调用数和音频时长。默认保护窗口 MUST 为 12 小时、最多 100 次调用、累计最多 360 分钟；完全相同音频整段缓存命中时 MUST NOT 消耗额度。额度不足时，系统 MUST 在任何远端分段开始前决定整项降级或失败，MUST NOT 主动生成部分 bcut、部分 Whisper 的混合字幕。

#### Scenario: 在线优先任务额度不足
- **WHEN** 150 分钟长音频预计会让 12 小时滚动调用数或音频时长超过保护上限，且策略为 `online_first`
- **THEN** 系统 MUST 移除本任务的 bcut 路径，按本地单 worker/WAV 档案处理全部分段，并记录预计恢复时间与预算 metadata

#### Scenario: 单引擎任务额度不足
- **WHEN** 相同条件下策略为 `single` 且引擎为 bcut
- **THEN** 系统 MUST 在上传前以结构化限流错误失败，MUST NOT 暗中切换本地引擎

#### Scenario: 整段缓存先于预算
- **WHEN** 相同音频和结果配置已存在完整 Cue 缓存
- **THEN** 系统 MUST 直接返回缓存，MUST NOT 新增 bcut 额度记录
