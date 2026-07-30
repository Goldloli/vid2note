# docker-deployment Specification

## Purpose

定义本地单容器构建、localhost 安全默认、非 root 运行、数据持久化和健康检查。确保开发、升级与重建过程中服务边界和用户数据始终可预期。

## Requirements

### Requirement: 多阶段单镜像

Dockerfile MUST 使用 Node 阶段构建前端，并使用 Python 3.11 slim 作为运行时。最终镜像 MUST 包含前端静态文件、FastAPI、FFmpeg、yt-dlp、ASR 与导图运行依赖。

#### Scenario: 构建生产镜像

- **WHEN** 执行 `docker build .`
- **THEN** 前端 SHALL 先通过 `npm ci` 和 Vite 构建，最终镜像 SHALL 不包含前端 `node_modules`

#### Scenario: 媒体工具可用

- **WHEN** 在镜像中执行 `ffmpeg -version` 和 `yt-dlp --version`
- **THEN** 两者 SHALL 成功退出

### Requirement: 模型不隐式下载

基础镜像 MUST NOT 在运行时自动下载 Whisper 模型。用户 SHALL 通过只读挂载提供本地模型路径。

#### Scenario: 未提供模型

- **WHEN** 用户未挂载和配置 Whisper 模型
- **THEN** 本地 ASR 就绪检查 SHALL 返回未就绪，不得在后台联网下载

### Requirement: localhost 安全默认

Compose MUST 将容器 `8765` 映射到宿主 `127.0.0.1:8761`，并 SHALL 允许通过 `VID2NOTE_PORT` 修改宿主端口。

#### Scenario: 默认访问

- **WHEN** 执行 `docker compose up -d`
- **THEN** 应用 SHALL 可从 `http://localhost:8761` 访问，且端口不得默认绑定所有宿主网卡

### Requirement: 单服务同源

FastAPI MUST 托管 `/api/v1` 和前端静态文件，用户无需额外启动 Nginx 或前端开发服务器。

#### Scenario: 前后端同源

- **WHEN** 浏览器访问应用并调用 `/api/v1/health`
- **THEN** 请求 SHALL 同源成功且不依赖宽松 CORS

### Requirement: 非 root 和最小权限

运行时进程 MUST 使用构建参数指定的非 root UID/GID。Compose SHALL 启用 `no-new-privileges` 并丢弃 Linux capabilities。

#### Scenario: 检查运行用户

- **WHEN** 执行 `docker compose exec vid2note id -u`
- **THEN** 返回值 SHALL 与配置的 `VID2NOTE_UID` 一致且不为 0

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

### Requirement: 健康检查

镜像 MUST 通过 `/api/v1/health` 提供 Docker HEALTHCHECK。

#### Scenario: 服务就绪

- **WHEN** FastAPI 启动且健康接口返回 2xx
- **THEN** 容器状态 SHALL 在启动宽限期后变为 healthy

### Requirement: 自动构建与发布

Pull Request MUST 构建生产镜像；版本标签 SHALL 触发 amd64/arm64 镜像发布到 GHCR，并生成构建来源证明。

#### Scenario: 推送版本标签

- **WHEN** 维护者推送 `v*` 标签
- **THEN** GitHub Actions SHALL 发布语义化标签和 `latest` 镜像
