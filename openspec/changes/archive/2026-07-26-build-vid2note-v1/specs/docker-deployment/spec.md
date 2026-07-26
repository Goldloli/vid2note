## ADDED Requirements

### Requirement: Dockerfile 基础镜像与内置工具链

Dockerfile MUST 基于 Python 官方镜像构建,并在单个镜像内 SHALL 内置视频处理六步流水线所需的全部命令行工具:yt-dlp(下载)、ffmpeg(音频提取)、whisper.cpp(ASR 引擎)、AsrTools(ASR 调度)。MinerU(PDF 对照)SHALL 作为可选层,通过构建参数开关,默认不构建进镜像以控制基础体积,仅在需要 PDF 对照能力时显式启用。

#### Scenario: 镜像内置下载与音频工具

- **WHEN** 从构建好的镜像启动容器并执行 `yt-dlp --version` 与 `ffmpeg -version`
- **THEN** 两个命令均 SHALL 返回有效版本号且退出码为 0,无「command not found」

#### Scenario: 镜像内置 ASR 工具链

- **WHEN** 从构建好的镜像启动容器并执行 whisper.cpp 推理命令以及 AsrTools 的入口命令
- **THEN** 两者均 SHALL 能被定位到可执行文件且无「command not found」

#### Scenario: MinerU 作为可选构建层

- **WHEN** 使用默认构建参数执行 `docker build`
- **THEN** MinerU 及其重型依赖 SHALL 不被安装进镜像
- **WHEN** 传入启用 MinerU 的构建参数重新构建
- **THEN** 镜像内 SHALL 可成功运行 MinerU 入口命令

### Requirement: docker-compose.yml 服务编排与端口

docker-compose.yml SHALL 定义后端服务与前端静态资源服务(可合并为单服务),MUST 将容器端口 8765 映射到宿主机端口 8765,使浏览器访问 `http://localhost:8765` 即可使用应用。compose 文件 MUST 显式声明命名 volume 用于持久化 SQLite 数据库与产物文件。

#### Scenario: 端口映射 8765

- **WHEN** 执行 `docker compose config` 解析 compose 文件
- **THEN** 输出 SHALL 包含将容器 8765 端口映射到宿主机 8765 端口的配置项

#### Scenario: 前端静态服务可用

- **WHEN** `docker compose up` 启动后向 `http://localhost:8765/` 发起 HTTP GET 请求
- **THEN** 响应 SHALL 返回 2xx 状态码与前端页面内容,而非连接拒绝或 404

#### Scenario: 命名 Volume 声明

- **WHEN** 执行 `docker compose config --volumes`
- **THEN** 输出 SHALL 列出至少一个用于持久化数据的命名 volume

### Requirement: 一条命令启动完整服务

执行单条 `docker compose up` 命令后,后端 API 服务(FastAPI:8765)与前端静态资源服务 SHALL 同时就绪;用户 MUST NOT 需要额外手动启动前端开发服务器或单独构建前端;浏览器访问 `http://localhost:8765` 即可加载完整界面并调用后端接口。

#### Scenario: 单命令拉起前后端

- **WHEN** 在项目根目录执行 `docker compose up -d` 后等待服务就绪
- **THEN** `docker compose ps` SHALL 显示所有服务状态为 running/healthy,且无服务处于退出或重启循环

#### Scenario: 后端 API 可达

- **WHEN** 服务启动后访问后端健康检查接口(例如 `GET http://localhost:8765/api/health` 或同等路径)
- **THEN** SHALL 返回 2xx 状态码,表明后端服务已就绪

#### Scenario: 前后端同源可达

- **WHEN** 浏览器访问 `http://localhost:8765` 加载界面,并在页面中触发一次调用后端的请求
- **THEN** 该后端调用 SHALL 成功返回,且 MUST NOT 因 CORS 或端口差异而失败

### Requirement: SQLite 与产物文件持久化

SQLite 数据库文件(任务记录、历史、prompt 库等)与处理产物(音频、字幕、Markdown 笔记、思维导图)MUST 通过命名 volume 持久化到宿主机;容器删除重建后数据 SHALL 保留。即执行 `docker compose down`(不带 `-v`)后再 `docker compose up`,历史任务与产物文件 SHALL 依然存在。

#### Scenario: 数据库跨容器重建保留

- **WHEN** 创建若干任务与历史记录后,执行 `docker compose down`(不带 `-v`)再执行 `docker compose up`
- **THEN** 应用界面 SHALL 仍展示此前创建的任务与历史,SQLite 数据库文件未被删除

#### Scenario: 产物文件跨容器重建保留

- **WHEN** 完整跑完一次六步流水线产生 Markdown 笔记与思维导图后,执行 `docker compose down`(不带 `-v`)再 `docker compose up`
- **THEN** 此前生成的产物文件 SHALL 仍在对应 volume 路径下可访问

#### Scenario: 显式 -v 清空 volume

- **WHEN** 执行 `docker compose down -v`
- **THEN** 持久化 volume 及其数据 SHALL 被删除,符合显式清空语义

### Requirement: 敏感配置外置注入

LLM API key(如 DeepSeek key)、可能用到的下载 cookie 等敏感配置 MUST NOT 被构建进镜像或写入镜像层;此类配置 SHALL 通过环境变量(`.env` 文件、`docker-compose.yml` 的 environment 字段)或应用内设置页在运行时注入。镜像本身 SHALL 保持无密钥状态,以便安全分发与多机复用。

#### Scenario: 镜像不含密钥

- **WHEN** 对构建出的镜像执行 `docker history` 并对镜像内常见配置路径搜索真实 API key 字符串
- **THEN** SHALL 不出现任何明文 API key 或 cookie 值

#### Scenario: 环境变量注入生效

- **WHEN** 在 `.env` 或 compose 的 environment 字段中设置 DeepSeek API key 后启动服务,并在后端配置校验处确认
- **THEN** 应用 SHALL 读取到该 key 并能成功发起对 DeepSeek 的调用

#### Scenario: 设置页注入并持久化

- **WHEN** 通过浏览器打开应用设置页,填入 API key/cookie 并保存
- **THEN** 配置 SHALL 被写入运行时持久化存储(SQLite 或 volume 内配置文件),重启容器后 SHALL 依然生效

#### Scenario: 缺失密钥的优雅降级

- **WHEN** 未注入任何 LLM API key 即启动应用
- **THEN** 应用 SHALL 正常启动并可访问界面,MUST NOT 因缺少 key 而启动即崩溃,仅在用户尝试调用 LLM 整理步骤时才提示需要配置 key

### Requirement: macOS arm64 优先支持

构建与运行 MUST 以 macOS arm64(Apple Silicon)为优先支持平台,确保在该平台上镜像构建、服务启动与六步流水线(尤其 whisper.cpp 推理)开箱即用。Dockerfile 与 compose 文件 SHALL 在 Apple Silicon 机器上不产生平台不兼容或需要手动改架构的问题。

#### Scenario: Apple Silicon 原生构建

- **WHEN** 在一台 macOS arm64 机器上执行 `docker compose build`
- **THEN** 构建 SHALL 成功完成,MUST NOT 通过 QEMU 模拟 x86,且最终镜像架构匹配 arm64/v8

#### Scenario: Apple Silicon 启动并跑通流水线

- **WHEN** 在 macOS arm64 上 `docker compose up` 后提交一个视频链接并跑完六步流水线
- **THEN** 流水线 SHALL 正常完成,whisper.cpp ASR 步骤在 arm64 下 MUST NOT 出现崩溃或非法指令错误
