## Why

当前 ASR 与设置页面只提供少量平铺字段，LLM 凭证又被整体脱敏，用户无法判断各提供商是否已配置、查看已保存密钥或验证连接。设置仍与任务数据混存在 SQLite 中，也不便于备份、迁移和公开项目时安全分享。

## What Changes

- 将设置中心重构为「通用 / LLM 服务 / 笔记生成 / 存储与清理 / 高级设置 / 关于」页签，保留独立 ASR 页面并增加「引擎 / Whisper 本地 / 外部 ASR / 转录策略」页签。
- 为 DeepSeek、通义千问、智谱 GLM、Kimi、百度千帆、豆包、MiniMax、Ollama 与一个自定义 OpenAI 兼容服务分别保存模型、Base URL 和凭证；每家提供默认模型，但允许用户直接编辑模型 ID。
- 普通查询只返回凭证的已配置状态、掩码和尾号；密钥输入框默认显示黑点，点击眼睛后通过独立接口按需读取明文；支持替换、清除与连接测试。
- 新增「简洁 / 适中 / 详细 / 超详细」四档笔记详细程度，并通过受维护的提示词策略影响直接生成和 PDF 对照两条笔记生成路径。
- 把非敏感设置写入仓库 `docker-compose.yml` 同目录下 bind mount 的 `data/config/settings.json`；凭证写入独立加密文件，密钥优先来自环境变量或 Docker secret，缺省时生成权限为 `0600` 的本机主密钥文件。
- 更新各内置 LLM 的默认模型和 Base URL，统一 OpenAI 兼容调用边界并修复自定义 Base URL 在超时客户端中被忽略的问题。
- 设置变更仍只影响此后创建的任务；应用首次升级时自动从 SQLite 迁移现有设置与凭证，迁移成功前不删除旧值。

## Capabilities

### New Capabilities

- `settings-management`: 定义页签化设置、LLM 提供商配置、凭证状态/按需查看/加密存储、外置设置文件、迁移与连接测试契约。

### Modified Capabilities

- `web-frontend`: 细化设置中心和独立 ASR 页的信息架构、字段状态、保存反馈与响应式交互。
- `note-generation`: 增加四档笔记详细程度，并将所选档位稳定映射到不同提示词约束。
- `speech-to-text`: 允许在独立 ASR 页配置并验证当前引擎实际支持的超时、语言、模型路径和外部服务参数。
- `storage-retention`: 将非敏感配置从 SQLite 权威态迁移为可备份的独立 JSON 文件，并规定与现有任务数据库的边界。
- `docker-deployment`: 规定设置文件、加密凭证与主密钥在 `./data` bind mount 中的持久化布局。

## Impact

- 后端：设置存储服务、加密凭证服务、设置与 LLM 测试 API、运行时设置快照、LLM 适配器、笔记提示词与迁移逻辑。
- 前端：设置页、ASR 页、公共表单组件、密钥交互、国际化文案和 API client。
- 数据：新增 `data/config/settings.json`、`data/config/credentials.enc` 与缺省 `data/config/master.key`；SQLite 保留任务、历史与产物引用。
- 依赖：增加经锁定版本的对称认证加密库；不引入外部密钥服务。

## Non-goals

- 不增加登录、多用户、远程访问或云端密钥托管。
- 不把 ASR 页面合并进设置中心，也不复制两套完整 ASR 配置入口。
- 不自动调用各厂商模型列表接口改变用户已填写的模型 ID。
- 不增加任意数量的自定义 LLM 实例；本次只提供一个受维护的 OpenAI 兼容自定义槽位。
- 不重写 ai_srt2md 的核心笔记流水线；只在既有 `SimpleProcessor` 与 prompt 库边界内注入详细程度策略。
