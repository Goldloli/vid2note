## MODIFIED Requirements

### Requirement: SQLite 任务持久化与外置设置

系统 MUST 使用单个 SQLite 数据库文件持久化任务记录、历史和产物引用，该数据库 MUST 位于持久化 Docker volume 内。用户非敏感设置 MUST 以 `${DATA_ROOT}/config/settings.json` 独立持久化，敏感凭证 MUST 以认证加密文件独立持久化；SQLite MUST NOT 继续作为新设置的权威态。数据库、设置文件和加密凭证在容器重建、镜像升级与重启后均 MUST 保留。

#### Scenario: 任务记录跨容器重启保留

- **WHEN** 创建并完成一个任务，再执行 `docker compose down` 与重新构建
- **THEN** 任务状态、产物引用和时间戳 MUST 仍可从 SQLite 查询且保持一致

#### Scenario: 外置配置跨容器重启保留

- **WHEN** 用户修改 SRT 保留策略和默认 LLM 并保存，再重建容器
- **THEN** `settings.json` MUST 保留新值，应用读取结果 MUST 与重建前一致

#### Scenario: 加密凭证跨容器重启保留

- **WHEN** 用户保存 LLM API Key 并重建容器，同时保留 `./data`
- **THEN** 应用 MUST 仍显示该 Key 已配置，并能使用同一主密钥解密调用

#### Scenario: 历史列表来自 SQLite

- **WHEN** 调用历史列表 API
- **THEN** 返回记录 MUST 来自 SQLite 而非设置 JSON 或进程内存

#### Scenario: 运行中任务重启后不悬空

- **WHEN** 一个任务处于运行中状态时容器被强制重启
- **THEN** 重启后该任务 MUST 被标记为可重跑或失败，MUST NOT 悬空

### Requirement: 分类型独立保留策略

系统 MUST 为视频、音频、SRT、笔记、截图五种产物分别提供「永久 / 7 天 / 30 天」保留策略。各值 MUST 写入独立 `settings.json`，修改任一类 MUST NOT 影响其他类；下一次清理扫描 MUST 读取新权威态并立即生效。

#### Scenario: 五类产物各自独立配置

- **WHEN** 将视频设为 7 天、笔记设为永久、截图设为 30 天并保存
- **THEN** `settings.json` MUST 分别保存三个值，未修改的音频和 SRT MUST 保持原值

#### Scenario: 首次启动提供合法默认值

- **WHEN** 首次启动且外置设置不存在
- **THEN** 五类产物 MUST 各自获得 `permanent / 7d / 30d` 中的合法默认值

#### Scenario: 非法取值被拒绝

- **WHEN** 请求保存不在合法枚举内的保留策略
- **THEN** 整个设置更新 MUST 被拒绝，现有 `settings.json` MUST 不变

#### Scenario: 配置变更立即对清理生效

- **WHEN** 用户修改某类保留策略并保存
- **THEN** 下一次清理扫描 MUST 按新文件值判断，MUST NOT 继续读取 SQLite 旧副本
