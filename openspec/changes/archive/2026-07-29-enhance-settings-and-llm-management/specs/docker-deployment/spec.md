## MODIFIED Requirements

### Requirement: 数据持久化

Compose MUST 把仓库 `./data` bind mount 到 `/app/data`。`data/tasks.db` SHALL 保存任务与历史，`data/config/settings.json` SHALL 保存非敏感设置，`data/config/credentials.enc` SHALL 保存加密凭证；缺少外部主密钥时 `data/config/master.key` SHALL 作为本机回退密钥且权限 MUST 为 `0600`。容器重建不得删除上述文件或任务产物，Git 忽略规则 MUST 防止运行配置、密文和主密钥被提交。

#### Scenario: 重建后读取历史与设置

- **WHEN** 完成任务并保存设置后执行 `docker compose down` 再重新构建启动
- **THEN** `tasks.db`、任务产物、`settings.json`、`credentials.enc` 与所用主密钥 MUST 保留，历史和设置 MUST 可正常读取

#### Scenario: 使用 Docker secret 主密钥

- **WHEN** 用户通过 `VID2NOTE_MASTER_KEY_FILE` 挂载可读的 Docker secret
- **THEN** 应用 MUST 使用该 secret 解密凭证，MUST NOT 生成 `data/config/master.key`

#### Scenario: 缺省主密钥安全生成

- **WHEN** 环境变量和 secret 文件均未提供且凭证存储首次初始化
- **THEN** 应用 SHALL 生成随机主密钥到 `data/config/master.key`，文件权限 MUST 为 `0600`，日志 MUST NOT 输出密钥内容

#### Scenario: 运行配置不进入 Git

- **WHEN** 应用已生成设置、密文和主密钥后执行 `git status`
- **THEN** 这些运行文件 MUST 被忽略，仓库只 SHALL 跟踪不含真实凭证的示例配置
