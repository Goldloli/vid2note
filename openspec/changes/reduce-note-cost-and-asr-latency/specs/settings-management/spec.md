## ADDED Requirements

### Requirement: ASR 性能设置默认值与兼容迁移

公开设置 MUST 为 bcut 提供可实际生效的性能默认值：在线并发 3、本地并发 1、在线目标分段 280 秒、缓存启用、缓存目录位于 `${DATA_ROOT}/asr_cache`、在线临时格式为 64 kbps MP3。旧配置中的单一 `concurrency` 和空 `cache_dir` MUST 在读取时兼容，并在用户下一次保存后规范化为新字段。

#### Scenario: 新安装获得优化默认值
- **WHEN** 数据卷中没有既有 ASR 配置
- **THEN** 设置响应与运行时 AsrConfig MUST 使用在线并发 3、本地并发 1、280 秒分段和已启用的数据卷缓存

#### Scenario: 旧配置不再压过全局值
- **WHEN** 旧配置含 `concurrency=1` 且全局任务并发为 3
- **THEN** 系统 MUST 将该字段解释为兼容值并迁移，后续 bcut 实际在线并发 MUST 来自 `online_concurrency`，不得继续被隐藏旧字段永久覆盖

#### Scenario: 缓存目录不允许逃逸数据卷
- **WHEN** 用户提交包含 `..` 或位于数据卷外的缓存目录
- **THEN** 后端 MUST 拒绝该配置并保持原设置不变
