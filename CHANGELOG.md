# 更新日志

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)；正式发布后的变更记录在此维护。

## [Unreleased]

### 新增

- 开源项目治理文件、贡献指南、安全策略、Issue/PR 模板。
- GitHub Actions 持续集成、容器发布和 Dependabot 配置。
- Ollama 本地 LLM 支持。
- 页签化设置中心与 ASR 管理页，包含引擎诊断、Provider 状态和连通性测试。
- DeepSeek、Qwen、GLM、Moonshot、Baidu、Doubao、MiniMax、Ollama 与自定义 OpenAI-compatible Provider 的独立配置。
- 简洁、适中、详细、超详细四档笔记详细度。
- 视频下载、音频提取、ASR、LLM 笔记、思维导图和清理组成的完整六步流水线。
- 任务持久化、SSE 进度、节点级重跑、产物保留策略和 Docker 单容器部署。

### 变更

- 实验性在线 ASR 的引擎 ID、实现、界面、API 和文档统一为 `bcut`；删除旧在线 provider 与签名服务分支，并明确不保证外部服务持续可用。
- 默认模型更新为各服务商当前常用模型 ID，同时仍允许用户直接编辑模型。
- 公开设置从 SQLite 迁移到可备份的 `data/config/settings.json`；旧设置会在首次启动时幂等迁移。

### 安全

- Docker Compose 默认只监听本机回环地址。
- 容器改为非 root 用户运行。
- Markdown 渲染增加 HTML 清洗。
- 上传文件增加类型与大小限制。
- 生产环境 500 响应不再泄露内部异常。
- LLM Key、外部 ASR Key 与 Bilibili Cookie 改为 Fernet 认证加密文件；密钥查看按字段白名单、显式操作和禁止缓存处理。

[Unreleased]: https://github.com/Goldloli/vid2note/commits/main
