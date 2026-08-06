## MODIFIED Requirements

### Requirement: 设置页处理选项

设置中心 MUST 提供界面语言、背景、输出语言、四档笔记详细程度、图片提取与质量、PDF 模式、并发任务数、分块大小、Temperature、最大重试次数和五类保留策略。详细程度 MUST 仅显示「简洁 / 适中 / 详细 / 超详细」，MUST NOT 显示「比较详细」。截图嵌入 SHALL 继续作为新建任务的逐任务选项。

#### Scenario: 笔记详细程度只显示四档
- **WHEN** 用户打开笔记生成设置
- **THEN** 页面 MUST 恰好显示简洁、适中、详细、超详细四项，保存超详细时 `note.detail_level` MUST 为 `exhaustive`

#### Scenario: 历史比较详细值加载
- **WHEN** 设置文件或历史任务暴露旧 `thorough` 值
- **THEN** 设置页 MUST 将其显示为超详细兼容状态，下一次保存 MUST 写入 `exhaustive`

#### Scenario: 保存反馈不使用阻塞弹窗
- **WHEN** 用户保存任一页签
- **THEN** 页面 MUST 以页内状态或 toast 展示保存中、成功或错误，MUST NOT 使用浏览器原生 `alert`

### Requirement: ASR 管理页

系统 MUST 保留独立 ASR 管理页及「引擎 / Whisper 本地 / 外部 ASR / 转录策略」四个页签。策略页 MUST 如实展示和编辑在线并发、本地并发、在线目标分段、缓存开关、缓存位置和在线临时音频格式；状态区 MUST 展示实际生效值。实验性在线 ASR 的名称 MUST 为 bcut，不得暗示官方、稳定或保证免费。

#### Scenario: 在线与本地策略分开展示
- **WHEN** 用户打开转录策略页签
- **THEN** 页面 MUST 分别显示在线并发与本地并发，MUST NOT 用单一“分段并发”掩盖两个引擎的不同实际行为

#### Scenario: 优化默认值可见
- **WHEN** 使用新安装默认配置
- **THEN** 页面 MUST 显示在线并发 3、本地并发 1、目标分段 280 秒、缓存已启用和 MP3 临时格式

#### Scenario: 配置保存后状态一致
- **WHEN** 用户保存合法 ASR 策略
- **THEN** 重新加载后的表单值与 `/asr/status` 实际生效值 MUST 一致

#### Scenario: 页面响应式可用
- **WHEN** 页面宽度缩小到手机尺寸
- **THEN** 页签、表单与操作按钮 MUST 重排为单列或可滚动布局，MUST NOT 出现水平页面溢出

## ADDED Requirements

### Requirement: 任务详情展示 ASR 性能摘要

任务详情在 ASR 节点含性能 metadata 时 MUST 展示缓存状态、分段数、并发数、上传大小和总耗时；历史任务无 metadata 时 MUST 保持现有节点展示且不出现空错误区块。

#### Scenario: 冷启动性能摘要
- **WHEN** 已完成任务的 ASR metadata 表明未命中缓存
- **THEN** 页面 MUST 显示冷启动、分段数、worker 数、上传大小和转录总耗时

#### Scenario: 热缓存性能摘要
- **WHEN** metadata 表明整段缓存命中
- **THEN** 页面 MUST 明确显示缓存命中和零上传，不得将秒级结果误标为在线冷启动速度
