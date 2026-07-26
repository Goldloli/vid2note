# speech-to-text Specification

## Purpose
TBD - created by archiving change build-vid2note-v1. Update Purpose after archive.
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

该 capability SHALL 支持三种可切换的 ASR 引擎：① 在线「必剪云接口」（对接必剪免费 ASR，作为默认优先引擎，默认 provider 为 `bcut`）；② 本地 whisper.cpp（CPU 推理 + int8 量化模型）；③ 外部 ASR endpoint（通过配置项指向用户自建的 HTTP ASR 服务，作为扩展位）。引擎来源 MUST 通过统一的配置项指定，且配置项 SHALL 能明确区分这三种来源。面向用户的文案 MUST 使用「必剪云接口」，MUST NOT 在 UI 中暴露 AsrTools / 剪映 等内部技术名词作为引擎名。

#### Scenario: 配置在线 AsrTools 引擎

- **WHEN** 引擎配置项设置为使用在线必剪云接口（默认 provider `bcut`），且网络与签名服务可用
- **THEN** 该 capability MUST 使用在线必剪云接口引擎完成转写，返回的 SRT 内容由该引擎产出

#### Scenario: 配置本地 whisper.cpp 引擎

- **WHEN** 引擎配置项设置为使用本地 whisper.cpp 引擎，且本地已就绪 int8 量化模型
- **THEN** 该 capability MUST 调用 whisper.cpp（以 CPU 推理 + int8 量化模型）完成转写，MUST NOT 发起任何网络请求

#### Scenario: 配置外部 ASR endpoint 引擎

- **WHEN** 引擎配置项设置为使用外部 ASR endpoint，且配置中提供了有效的 HTTP endpoint 地址
- **THEN** 该 capability MUST 将音频发送至该外部 endpoint，接收其返回结果并转换为 SRT；endpoint 地址 MUST 来自配置项而非硬编码

### Requirement: 引擎选择策略

该 capability SHALL 支持两种引擎选择策略:「在线优先,失败转本地」(默认)与「指定单一引擎」。在「在线优先」策略下,在线 AsrTools 为首选,当其不可用时自动降级到本地 whisper.cpp;在「指定单一引擎」策略下,MUST 只使用配置中指定的那一种引擎,不进行任何降级。

#### Scenario: 在线优先策略下在线引擎可用

- **WHEN** 引擎策略配置为「在线优先,失败转本地」,且在线 AsrTools 引擎可用
- **THEN** 该 capability MUST 使用在线 AsrTools 完成转写,MUST NOT 触发本地引擎

#### Scenario: 在线优先策略下在线引擎失败转本地

- **WHEN** 引擎策略配置为「在线优先,失败转本地」,在线 AsrTools 引擎调用失败(如服务不可用或鉴权失败),且本地 whisper.cpp 可用
- **THEN** 该 capability MUST 自动切换到本地 whisper.cpp 完成转写,最终仍产出完整 SRT,并记录一次降级事件

#### Scenario: 指定单一引擎策略不降级

- **WHEN** 引擎策略配置为「指定单一引擎」且指定为在线 AsrTools,而在线引擎调用失败
- **THEN** 该 capability SHALL NOT 自动降级到本地引擎,MUST 直接以该引擎失败结束并返回错误

### Requirement: 长音频 VAD 分段并行转录

对于超过单次转写阈值的音频,该 capability SHALL 使用 VAD(语音活性检测)按静音切分为多段,对各段并行调用 ASR 引擎转录,再按每段相对音频起始的时间偏移量,将该段字幕时间戳叠加偏移后拼回,产出一份时间戳连续且单调递增的完整 SRT。分段与拼合对调用方 MUST 透明(调用方只看到一份完整的 SRT)。

#### Scenario: 短音频不触发分段

- **WHEN** 输入音频时长小于单次转写阈值(如 5 分钟)
- **THEN** 该 capability MUST 直接将整段音频送入 ASR 引擎,MUST NOT 进行 VAD 分段,产出单份 SRT

#### Scenario: 长音频按静音分段并行转录

- **WHEN** 输入音频时长超过单次转写阈值,且 VAD 在静音处成功切分出多段
- **THEN** 该 capability MUST 对各段并行调用 ASR 引擎(多段可同时进行转录),最终拼合为一份 SRT

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

当在线 ASR 引擎(在线 AsrTools 或外部 endpoint)出现服务不可用、超时、限流(HTTP 429)或鉴权失败等情形时,该 capability SHALL 自动降级到可用的备选引擎(在「在线优先」策略下降级到本地 whisper.cpp),并 MUST 在日志中记录每一次降级事件,日志内容 SHALL 包含触发降级的原因(失败类型或 HTTP 状态码)、原引擎、降级目标引擎与时间戳。

#### Scenario: 在线引擎限流时降级并记录

- **WHEN** 在线 AsrTools 引擎返回限流(HTTP 429)或服务端错误,且引擎策略为「在线优先,失败转本地」
- **THEN** 该 capability MUST 自动降级到本地 whisper.cpp 完成转写,且 MUST 在日志中记录一条降级事件,事件中包含触发原因(429/限流)、原引擎(AsrTools)、目标引擎(whisper.cpp)

#### Scenario: 在线引擎超时时降级并记录

- **WHEN** 在线引擎在配置的超时时间内未返回结果(网络超时),且引擎策略为「在线优先,失败转本地」
- **THEN** 该 capability MUST 中止该次在线调用并降级到本地引擎完成转写,且 MUST 在日志中记录一次超时降级事件

#### Scenario: 所有引擎均不可用时报错

- **WHEN** 在线引擎失败,且本地 whisper.cpp 同样不可用(如模型文件缺失),已无可用引擎
- **THEN** 该 capability MUST 抛出明确的「无可用 ASR 引擎」错误并终止,MUST NOT 返回部分 SRT,且终止前 SHALL 在日志中记录已尝试的引擎与各自失败原因

