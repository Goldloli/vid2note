# speech-to-text Specification

## Purpose
定义在线、本地和外部 ASR 引擎、降级策略、VAD 分段与 SRT 输出行为。确保不同音频长度和故障条件下都能得到可追踪、时间戳单调的转录结果。
## Requirements
### Requirement: 输入输出契约

speech-to-text capability 的核心契约是:接收一个上游流水线(音频提取步骤)产出的本地音频文件作为输入,产出一份符合标准 SRT 格式、且每条字幕均带时间戳的字幕文件。输入音频文件路径 SHALL 由调用方提供;输出 SRT 文件路径 MUST 返回给调用方,供后续 LLM 整理笔记步骤消费。整份 SRT 的时间戳 MUST 单调递增且覆盖音频的完整时长。

#### Scenario: 正常音频文件转写为 SRT

- **WHEN** 调用方提供一个有效的本地音频文件路径(如 `audio.wav` 或 `audio.mp3`),时长 60 秒
- **THEN** 该 capability MUST 返回一个 `.srt` 文件路径,其内容符合标准 SRT 格式(序号 + `HH:MM:SS,mmm --> HH:MM:SS,mmm` 时间戳行 + 字幕文本 + 空行),且首条字幕起始时间戳接近 00:00:00,末条结束时间戳接近音频实际时长

#### Scenario: 输入文件不存在时报错

- **WHEN** 调用方提供的音频文件路径在文件系统上不存在
- **THEN** 该 capability SHALL 抛出明确的输入校验错误并终止,MUST NOT 创建空的 SRT 文件,错误信息中 MUST 包含缺失的文件路径

#### Scenario: SRT 时间戳单调递增

- **WHEN** 对任意有效音频完成转写后解析输出的 SRT
- **THEN** 每条字幕的结束时间戳 MUST 大于等于其起始时间戳,且每条字幕的起始时间戳 MUST 大于等于上一条字幕的起始时间戳(时间戳严格不回退)

### Requirement: 三种 ASR 引擎与统一配置

该 capability SHALL 支持三种可切换的 ASR 引擎：① 在线 `bcut`（默认优先引擎）；② 本地 whisper.cpp（CPU 推理 + int8 量化模型）；③ 外部 ASR endpoint（通过配置项指向用户自建的 HTTP ASR 服务，作为扩展位）。引擎来源 MUST 通过统一配置项指定并明确区分。面向用户的文案 MUST 使用「bcut」，只描述在线识别用途、无需本地模型及自动切换行为，MUST NOT 展示内部额度、实验性或稳定性判断，也不得在未经真实探活时显示恒定就绪状态。

#### Scenario: 配置在线 bcut 引擎

- **WHEN** 引擎配置项设置为使用在线 `bcut`（默认 provider `bcut`），且外部服务可用
- **THEN** 该 capability MUST 使用在线 `bcut` 引擎完成转写，返回的 SRT 内容由该引擎产出

#### Scenario: 配置本地 whisper.cpp 引擎

- **WHEN** 引擎配置项设置为使用本地 whisper.cpp 引擎，且本地已就绪 int8 量化模型
- **THEN** 该 capability MUST 调用 whisper.cpp（以 CPU 推理 + int8 量化模型）完成转写，MUST NOT 发起任何网络请求

#### Scenario: 配置外部 ASR endpoint 引擎

- **WHEN** 引擎配置项设置为使用外部 ASR endpoint，且配置中提供了有效的 HTTP endpoint 地址
- **THEN** 该 capability MUST 将音频发送至该外部 endpoint，接收其返回结果并转换为 SRT；endpoint 地址 MUST 来自配置项而非硬编码

### Requirement: 引擎选择策略

该 capability SHALL 支持两种引擎选择策略:「在线优先,失败转本地」(默认)与「指定单一引擎」。在「在线优先」策略下,在线 `bcut` 为首选,当其不可用时自动降级到本地 whisper.cpp;在「指定单一引擎」策略下,MUST 只使用配置中指定的那一种引擎,不进行任何降级。

#### Scenario: 在线优先策略下在线引擎可用

- **WHEN** 引擎策略配置为「在线优先,失败转本地」,且在线 `bcut` 引擎可用
- **THEN** 该 capability MUST 使用在线 `bcut` 完成转写,MUST NOT 触发本地引擎

#### Scenario: 在线优先策略下在线引擎失败转本地

- **WHEN** 引擎策略配置为「在线优先,失败转本地」,在线 `bcut` 引擎调用失败(如服务不可用或协议变化),且本地 whisper.cpp 可用
- **THEN** 该 capability MUST 自动切换到本地 whisper.cpp 完成转写,最终仍产出完整 SRT,并记录一次降级事件

#### Scenario: 指定单一引擎策略不降级

- **WHEN** 引擎策略配置为「指定单一引擎」且指定为在线 `bcut`,而在线引擎调用失败
- **THEN** 该 capability SHALL NOT 自动降级到本地引擎,MUST 直接以该引擎失败结束并返回错误

### Requirement: 长音频 VAD 分段并行转录

对于超过单次转写阈值的音频，该 capability SHALL 使用 VAD 按静音切分为多段并按引擎选择并发和临时格式。bcut 在线路径 MUST 默认使用 280 秒目标分段、295 秒硬上限、3 个有界 worker 和 16 kHz 单声道 64 kbps MP3；本地 Whisper 路径 MUST 默认单 worker 并可使用无损 WAV。各段字幕按起始偏移拼回，最终 SRT 时间戳 MUST 连续且单调递增。分段与拼合对调用方 MUST 透明。

#### Scenario: 短音频不触发分段

- **WHEN** 输入音频时长小于单次转写阈值(如 5 分钟)
- **THEN** 该 capability MUST 直接将整段音频送入 ASR 引擎,MUST NOT 进行 VAD 分段,产出单份 SRT

#### Scenario: bcut 长音频使用在线档案

- **WHEN** 约 150 分钟音频由 bcut 在线转录且使用默认配置
- **THEN** 系统 MUST 以约 280 秒为目标在静音处切分，默认最多同时执行 3 个在线段任务，上传临时文件 MUST 为语音 MP3 而非 PCM WAV

#### Scenario: 本地 Whisper 保持单并发

- **WHEN** bcut 降级到本地 Whisper 或任务指定本地引擎
- **THEN** 本地转录 MUST 使用单 worker 和本地适用的音频格式，MUST NOT 因在线并发配置同时运行多个 CPU 模型调用

#### Scenario: 分段时间戳按偏移拼回

- **WHEN** 一个从音频第 300 秒开始、第 360 秒结束的片段被单独转录,该片段内 ASR 产出的某条字幕相对片段起始为 10 秒
- **THEN** 拼合后的 SRT 中该条字幕的起始时间戳 MUST 为 00:05:10(即 310 秒,偏移叠加后),整份 SRT 时间戳连续、无错位

#### Scenario: 拼合后 SRT 连续单调

- **WHEN** 长音频完成分段转录并按偏移拼合
- **THEN** 最终 SRT 中相邻字幕的时间戳 MUST 单调递增、不存在时间回退,跨段拼接处不存在时间戳重叠或空洞

### Requirement: 字幕来源一律 ASR

该 capability 产出的字幕内容 MUST 完全来自对音频的 ASR 转录结果。v1 MUST NOT 抓取、MUST NOT 使用任何视频平台的官方字幕(CC)。MUST NOT 存在从视频源直接拉取已有字幕并作为产出的代码路径。

#### Scenario: 不使用官方字幕

- **WHEN** 视频源(如 B 站 / YouTube)本身提供官方字幕,且流水线请求该视频的字幕
- **THEN** 该 capability MUST 通过对音频做 ASR 产出字幕,即使官方字幕存在也 MUST NOT 将官方字幕作为 SRT 内容

#### Scenario: 无 ASR 结果时不伪造字幕

- **WHEN** ASR 引擎对某段音频未识别出任何语音内容(如纯静音段)
- **THEN** 该 capability MUST NOT 为该段生成伪造时间戳的字幕条目,该段在 SRT 中可如实省略或留空,但 MUST NOT 编造字幕文本

### Requirement: 在线引擎降级与日志记录

当在线 ASR 引擎（`bcut` 或外部 endpoint）出现服务不可用、超时、限流（HTTP 429）、协议变化或鉴权失败等情形时，该 capability SHALL 对可重试的瞬时错误先执行有限次带退避重试，重试用尽后才降级到可用备选引擎；412/429 的任务级熔断与共享冷却规则除外。每次实际降级 MUST 记录原因、原引擎、目标引擎与时间戳。

#### Scenario: 瞬时错误重试成功不降级

- **WHEN** 在线 `bcut` 首次返回可重试的 429 或 5xx，且有限重试内成功
- **THEN** 该 capability MUST 返回成功结果，MUST NOT 触发或记录降级

#### Scenario: 在线引擎限流时降级并记录

- **WHEN** 在线 `bcut` 引擎返回限流(HTTP 429)或服务端错误,且引擎策略为「在线优先,失败转本地」
- **THEN** 该 capability MUST 自动降级到本地 whisper.cpp 完成转写,且 MUST 在日志中记录一条降级事件,事件中包含触发原因(429/限流)、原引擎(`bcut`)、目标引擎(whisper.cpp)

#### Scenario: 在线引擎超时时降级并记录

- **WHEN** 在线引擎在配置的超时时间内未返回结果(网络超时),且引擎策略为「在线优先,失败转本地」
- **THEN** 该 capability MUST 中止该次在线调用并降级到本地引擎完成转写,且 MUST 在日志中记录一次超时降级事件

#### Scenario: 所有引擎均不可用时报错

- **WHEN** 在线引擎失败,且本地 whisper.cpp 同样不可用(如模型文件缺失),已无可用引擎
- **THEN** 该 capability MUST 抛出明确的「无可用 ASR 引擎」错误并终止,MUST NOT 返回部分 SRT,且终止前 SHALL 在日志中记录已尝试的引擎与各自失败原因

### Requirement: ASR 引擎参数可配置与校验

独立 ASR 页面 SHALL 允许配置 bcut 超时、在线目标分段、在线并发、缓存开关和在线临时格式；Whisper 模型路径、语言和本地并发；外部 endpoint、凭证与超时。后端 MUST 对 URL、数值范围、格式枚举和并发范围做白名单校验，非法请求 MUST 整体拒绝。旧 `concurrency` MUST 只作为兼容输入，新设置 MUST 使用 `online_concurrency` 与 `local_concurrency`。`whisper_device=cpu` 与 `whisper_compute_type=int8` SHALL 作为当前实现约束展示。

#### Scenario: Whisper 配置用于引擎构造

- **WHEN** 用户保存模型路径、binary 和识别语言后选择 Whisper 本地
- **THEN** 后续任务构造 `WhisperCppEngine` 时 MUST 使用这些值，且仍 MUST 使用 CPU / int8

#### Scenario: 外部 ASR 凭证从加密存储解析

- **WHEN** 用户保存外部 endpoint、API Key 和超时后创建外部 ASR 任务
- **THEN** endpoint 与超时 MUST 来自非敏感设置，API Key MUST 在运行时从加密凭证存储解析并用于 Authorization，普通设置响应 MUST NOT 返回明文

#### Scenario: VAD 数值非法时整体拒绝

- **WHEN** 用户把 VAD 阈值设为负数或把分段并发设为 0
- **THEN** 后端 MUST 返回校验错误，原 ASR 配置 MUST 保持完整不变

#### Scenario: 本地固定能力如实展示

- **WHEN** 用户打开 Whisper 本地页签
- **THEN** 页面 MUST 明确展示当前固定为 CPU 与 int8，MUST NOT 提供实际不会生效的 GPU 或其他量化选择

#### Scenario: 在线与本地并发分别生效

- **WHEN** 配置在线并发 3、本地并发 1
- **THEN** bcut 分段线程池 MUST 使用最多 3 个 worker，Whisper MUST 使用 1 个 worker，全局任务并发 MUST NOT 覆盖二者

#### Scenario: 旧并发配置迁移

- **WHEN** 旧设置只含 `concurrency`
- **THEN** 后端 MUST 安全读取该值并在下一次保存时写入新字段，状态端点 MUST 展示实际生效的在线与本地并发

#### Scenario: 非法格式整体拒绝

- **WHEN** 用户提交不支持的在线临时格式或越界并发
- **THEN** 后端 MUST 返回校验错误且原 ASR 配置完整不变

### Requirement: ASR 结果文件级缓存

该 capability SHALL 对分段 ASR 结果提供文件级缓存；缓存键 MUST 区分引擎、音频内容与识别语言，缓存关闭时 MUST 不读写缓存。命中结果对调用方透明，不同音频或配置 MUST NOT 误命中。

#### Scenario: 同音频命中缓存跳过上传

- **WHEN** 相同音频以相同引擎与语言再次转录且缓存开启
- **THEN** 系统 MUST 直接返回缓存结果，MUST NOT 再次上传或轮询

#### Scenario: 不同音频或缓存关闭不复用

- **WHEN** 音频内容、引擎、语言任一不同，或缓存开关关闭
- **THEN** 系统 MUST 正常执行转录，MUST NOT 错误复用缓存结果

### Requirement: VAD 前整段音频内容缓存

系统 MUST 在 VAD 检测之前查询整段音频缓存。缓存键 MUST 使用强内容哈希并包含引擎、语言、缓存 schema 版本及影响识别结果的配置；缓存值 MUST 原子写入数据卷。命中时 MUST 跳过 VAD、切片、上传和轮询，损坏时 MUST 忽略并执行冷启动。

#### Scenario: 完全相同音频热命中

- **WHEN** 同一音频和相同识别配置第二次执行
- **THEN** 系统 MUST 直接从整段缓存恢复 Cue 并生成 SRT，MUST NOT 创建任何上传任务

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
- **THEN** 多个分段的 HTTP 客户端 MUST 复用连接池，同时每段任务 ID 与上传状态 MUST 相互隔离

#### Scenario: 创建任务失败不被隐式重复

- **WHEN** 创建任务 POST 的响应不确定
- **THEN** urllib3 自动重试 MUST NOT 再次发送该 POST，系统 MUST 进入受控外层重试或降级

#### Scenario: 远端限流触发本任务熔断

- **WHEN** 任一 bcut worker 收到 HTTP 412 或 429
- **THEN** 系统 MUST 停止本任务后续分段继续尝试 bcut，MUST NOT 立即重试同一远端任务

### Requirement: bcut 滚动额度整项预检

系统 MUST 在整项冷启动任务开始前，以持久化滚动窗口预留预计 bcut 调用数和音频时长。默认保护窗口 MUST 为 12 小时、最多 100 次调用、累计最多 360 分钟；完全相同音频整段缓存命中时 MUST NOT 消耗额度。额度不足时 MUST 在任何远端分段开始前决定整项降级或失败。

#### Scenario: 在线优先任务额度不足

- **WHEN** 长音频预计超过滚动调用数或音频时长上限，且策略为 `online_first`
- **THEN** 系统 MUST 跳过 bcut，按本地单 worker 档案处理全部分段并记录预算 metadata

#### Scenario: 单引擎任务额度不足

- **WHEN** 相同条件下策略为 `single` 且引擎为 bcut
- **THEN** 系统 MUST 在上传前以结构化限流错误失败，MUST NOT 暗中切换本地引擎

#### Scenario: 整段缓存先于预算

- **WHEN** 相同音频和结果配置已存在完整 Cue 缓存
- **THEN** 系统 MUST 直接返回缓存，MUST NOT 新增 bcut 额度记录

### Requirement: bcut 限流单飞探测与共享冷却

当长音频在在线优先策略下选择 bcut 时，系统 MUST 先以一个真实分段串行探测，成功后才 SHALL 并发处理剩余在线分段。任一探测或在线分段收到 HTTP 412/429 时，系统 MUST 在任务内停用 bcut、只记录一次降级，并将冷却共享给同进程及后续任务；冷却期内新任务 MUST 跳过 bcut。

#### Scenario: 远端正常时首段成功后并发

- **WHEN** 长音频被切分为多个在线分段且 bcut 首段探测成功
- **THEN** 首段结果 MUST 纳入最终 SRT，剩余分段 SHALL 按在线并发配置处理

#### Scenario: 首段限流时剩余分段不再撞接口

- **WHEN** bcut 首段探测返回 HTTP 412 或 429，策略为在线优先
- **THEN** 当前任务 MUST 只记录一次降级，剩余分段 MUST 由本地引擎完成

#### Scenario: 多任务共享远端冷却

- **WHEN** 一个任务确认 bcut 处于 412/429 冷却，另一个任务随后开始 ASR
- **THEN** 后续任务 MUST 在在线请求前发现冷却并跳过 bcut

#### Scenario: 冷却过期后恢复探测

- **WHEN** 共享限流冷却超过滚动窗口
- **THEN** 新任务 SHALL 重新执行一次首段探测，MUST NOT 永久停用在线引擎

### Requirement: 本地 CPU Whisper 跨任务容量调度

单进程运行时，系统 MUST 将本地 CPU Whisper 作为容量为 1 的共享资源。任务首次选择本地 Whisper 后 MUST 获取任务级执行槽，并在全部本地分段完成、取消或失败后释放；不同任务的本地 Whisper 推理 MUST NOT 同时运行，在线 bcut 分段 MUST NOT 受此限制。

#### Scenario: 两个本地长任务不同时推理

- **WHEN** 两个任务同时进入本地 Whisper 长音频转写
- **THEN** 最多一个任务 SHALL 执行本地推理，另一个任务 MUST 可取消地等待

#### Scenario: 在线任务保持并发

- **WHEN** 多个任务的 bcut 探测均成功且无需本地降级
- **THEN** 这些任务 SHALL 继续按在线并发配置工作，MUST NOT 因本地执行槽而串行化

#### Scenario: 等待本地槽时可以取消

- **WHEN** 任务等待本地执行槽时收到取消请求
- **THEN** 等待 MUST 及时终止，MUST NOT 泄漏或错误释放其他任务持有的槽

#### Scenario: 异常后释放本地槽

- **WHEN** 持有本地槽的任务发生异常
- **THEN** 系统 MUST 在清理路径释放执行槽，使后续任务继续

### Requirement: ASR 运行时协调指标

系统 SHALL 在 ASR 节点 metadata 中记录在线探测、共享冷却跳过和本地槽等待情况，并保持既有引擎尝试、成功分段、降级次数与耗时字段兼容。

#### Scenario: 本地等待时间可观测

- **WHEN** 一个任务因其他任务占用本地执行槽而等待
- **THEN** ASR metadata MUST 包含非负等待秒数和已取得执行槽标志

#### Scenario: 冷却跳过可观测

- **WHEN** 任务因共享 bcut 冷却直接使用本地引擎
- **THEN** ASR metadata MUST 标记未发起在线探测并因冷却跳过 bcut
