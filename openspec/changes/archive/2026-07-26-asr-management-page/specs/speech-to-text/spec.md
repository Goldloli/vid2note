## MODIFIED Requirements

### Requirement: 三种 ASR 引擎与统一配置

该 capability SHALL 支持三种可切换的 ASR 引擎：① 实验性在线「bcut」（作为默认优先引擎，默认 provider 为 `bcut`，依赖外部服务且不保证持续可用）；② 本地 whisper.cpp（CPU 推理 + int8 量化模型）；③ 外部 ASR endpoint（通过配置项指向用户自建的 HTTP ASR 服务，作为扩展位）。引擎来源 MUST 通过统一的配置项指定，且配置项 SHALL 能明确区分这三种来源。面向用户的文案 MUST 使用「bcut」，MUST NOT 把该能力描述为官方、稳定或保证免费的云服务。

#### Scenario: 配置在线 bcut 引擎

- **WHEN** 引擎配置项设置为使用在线 bcut（默认 provider `bcut`），且外部服务可用
- **THEN** 该 capability MUST 使用在线 bcut 引擎完成转写，返回的 SRT 内容由该引擎产出

#### Scenario: 配置本地 whisper.cpp 引擎

- **WHEN** 引擎配置项设置为使用本地 whisper.cpp 引擎，且本地已就绪 int8 量化模型
- **THEN** 该 capability MUST 调用 whisper.cpp（以 CPU 推理 + int8 量化模型）完成转写，MUST NOT 发起任何网络请求

#### Scenario: 配置外部 ASR endpoint 引擎

- **WHEN** 引擎配置项设置为使用外部 ASR endpoint，且配置中提供了有效的 HTTP endpoint 地址
- **THEN** 该 capability MUST 将音频发送至该外部 endpoint，接收其返回结果并转换为 SRT；endpoint 地址 MUST 来自配置项而非硬编码
