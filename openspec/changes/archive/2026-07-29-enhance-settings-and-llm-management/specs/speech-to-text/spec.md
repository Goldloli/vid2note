## ADDED Requirements

### Requirement: ASR 引擎参数可配置与校验

独立 ASR 页面 SHALL 允许配置现有 `AsrConfig` 实际消费的参数：bcut 超时；Whisper 模型路径、可选 binary 与识别语言；外部 ASR endpoint、API Key 与超时；VAD 触发阈值、目标分段时长、分段并发和请求超时。后端 MUST 对 URL、数值范围和枚举做白名单校验，非法请求 MUST 整体拒绝且不得部分写入。`whisper_device=cpu` 与 `whisper_compute_type=int8` SHALL 作为当前实现约束展示，MUST NOT 伪装成可用的 GPU 选项。

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
