# 配置与数据

## 配置优先级

运行时按以下顺序取值：

1. 任务创建时显式选择的 Provider、模型、ASR 引擎和笔记详细度；
2. `data/config/settings.json` 中由设置页保存的公开设置；
3. 环境变量；
4. 内置默认值。

设置只影响之后创建的新任务，不会静默修改历史任务。首次使用新版配置系统时，旧 SQLite 设置会幂等迁移；只有新文件写入并回读校验成功后，旧敏感字段才会从 SQLite 删除。

## 设置中心

设置页分为六个页签：

- **通用**：界面语言、主题、背景、并发任务数；
- **LLM**：九个 Provider 的模型、接口地址、超时、凭证状态和连接测试；
- **笔记**：输出语言、四档详细度、截图与图片质量；
- **存储**：五类产物的保留周期与当前占用；
- **高级**：分块大小、温度、重试次数；
- **关于**：版本、数据路径、公开设置路径、加密文件路径和主密钥来源。

ASR 页面另外提供“引擎 / Whisper / 外部服务 / 策略”页签。模型路径必须填写容器内绝对路径；外部 ASR endpoint 必须是 HTTP(S) 地址。

笔记详细度共有四档：

| 界面名称 | 设置值 | 行为 |
| --- | --- | --- |
| 简洁 | `concise` | 只保留结论、关键论据和必要步骤 |
| 适中 | `balanced` | 在结构与信息量之间保持平衡 |
| 详细 | `detailed` | 展开概念、推理、例子与步骤 |
| 超详细 | `exhaustive` | 尽可能完整地覆盖原始材料，但仍禁止编造 |

## LLM Provider

下表是新安装的默认值。模型 ID 和 Base URL 均可在设置页覆盖，自定义槽位必须自行填写二者。

| Provider | 默认模型 ID | 默认 Base URL |
| --- | --- | --- |
| DeepSeek | `deepseek-v4-flash` | `https://api.deepseek.com/v1` |
| 通义千问 | `qwen3.7-plus` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 智谱 GLM | `glm-5.2` | `https://open.bigmodel.cn/api/paas/v4/` |
| Kimi / Moonshot | `kimi-k2.6` | `https://api.moonshot.cn/v1` |
| 百度千帆 | `ernie-5.0` | `https://qianfan.baidubce.com/v2` |
| 豆包 | `doubao-seed-2-0-lite-260215` | `https://ark.cn-beijing.volces.com/api/v3` |
| MiniMax | `MiniMax-M2.7` | `https://api.minimaxi.com/v1` |
| Ollama | `qwen3.5` | `http://host.docker.internal:11434/v1` |
| 自定义兼容服务 | 无 | 无 |

这些默认值依据服务商官方文档在 2026-07-29 核对：

- [DeepSeek Models](https://api-docs.deepseek.com/api/list-models)
- [阿里云百炼文本生成模型](https://help.aliyun.com/zh/model-studio/text-generation-model)
- [智谱 GLM-5.2](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.2)
- [Kimi Models](https://platform.kimi.ai/docs/models)
- [百度千帆 ERNIE 5.0](https://intl.cloud.baidu.com/en/doc/qianfan/s/7m95lyy43-intl-en)
- [豆包模型列表](https://www.volcengine.com/docs/82379/1795150)
- [MiniMax API Overview](https://platform.minimaxi.com/docs/api-reference/api-overview)
- [Ollama qwen3.5](https://ollama.com/library/qwen3.5)

服务商可能调整模型可用性或要求使用控制台中的 endpoint ID；遇到模型不存在时，以当前账号控制台和官方文档为准，直接编辑模型 ID 即可。

## Docker 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VID2NOTE_PORT` | `8761` | 宿主访问端口 |
| `VID2NOTE_UID` / `VID2NOTE_GID` | `1000` | Linux 非 root 容器用户 |
| `DATA_ROOT` | `/app/data` | SQLite、设置和产物根目录 |
| `LLM_PROVIDER` | `deepseek` | 未保存设置时的默认 LLM |
| `<PROVIDER>_API_KEY` | 空 | 对应 Provider 的 Key |
| `<PROVIDER>_MODEL` | Provider 默认值 | 未保存模型时的默认值 |
| `<PROVIDER>_BASE_URL` | Provider 默认值 | 未保存地址时的默认值 |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434/v1` | 宿主 Ollama |
| `EXTERNAL_ASR_API_KEY` | 空 | 外部 ASR Key 的环境变量回落 |
| `BILIBILI_COOKIE` | 空 | Bilibili Cookie 的环境变量回落 |
| `VID2NOTE_MASTER_KEY` | 空 | 直接提供 Fernet 主密钥 |
| `VID2NOTE_MASTER_KEY_FILE` | 自动探测 | 主密钥文件；推荐 Docker Secret |
| `MAX_MEDIA_UPLOAD_MB` | `2048` | 单个音视频上传上限 |
| `MAX_PDF_UPLOAD_MB` | `100` | 单个 PDF 上传上限 |
| `ALLOW_PRIVATE_URLS` | `false` | 是否允许 localhost/内网直链 |

所有示例见根目录 `.env.example`。不建议把真实 Key 直接写进会提交或共享的 `.env`。

## 文件存储与主密钥

```text
data/
├── tasks.db
├── config/
│   ├── settings.json
│   ├── settings.json.last-good
│   ├── credentials.enc
│   └── master.key
└── videos/ audio/ srt/ notes/ screenshots/
```

- `settings.json` 是版本化公开设置，不含 Key、Cookie 或外部 ASR 凭证；
- `settings.json.last-good` 是最近一次成功写入的同内容副本；
- `credentials.enc` 使用 Fernet 认证加密，篡改或错误主密钥会被拒绝；
- `master.key` 仅在没有环境变量或外部密钥文件时自动生成；
- 上述设置、密文和默认主密钥文件权限均为 `0600`。

主密钥优先级为：

1. `VID2NOTE_MASTER_KEY`；
2. `VID2NOTE_MASTER_KEY_FILE`；
3. `/run/secrets/vid2note_master_key`；
4. 已存在的 `data/config/master.key`；
5. 首次启动自动生成 `master.key`。

将 `credentials.enc` 与 `master.key` 放在同一目录主要避免意外明文泄露，并不等价于主机级 Secret Manager。生产部署应把主密钥作为 Docker Secret 单独挂载；备份和恢复时必须让密文与对应主密钥成对。

## 凭证交互

设置页默认只显示脱敏值和“已配置 / 未配置 / 来自环境变量”等状态。空白保存不会覆盖已有凭证；清除凭证需要二次确认。点击输入框右侧眼睛后，前端只请求当前字段的明文，并在切换 Provider、切换页签、离开页面或 60 秒后重新隐藏。

连接测试会发起最小真实请求，并只返回分类后的结果。服务端不会把 Key 写入日志或普通设置响应。由于应用无登录，不要把端口暴露到不可信网络。

## Ollama

宿主机准备模型：

```bash
ollama pull qwen3.5
```

环境变量示例：

```dotenv
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3.5
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

Ollama 不需要 API Key。若服务位于另一台机器，改为其 OpenAI-compatible `/v1` 地址，并确保网络和防火墙允许访问。

## 本地 Whisper

项目支持 faster-whisper 模型目录和 whisper.cpp 模型文件 / `whisper-cli`，模型不会自动下载。挂载示例：

```yaml
services:
  vid2note:
    volumes:
      - ./models:/models:ro
```

在 ASR 页设置 `/models/...` 容器内路径，并运行就绪检查。

## Linux 文件权限

默认镜像使用 UID/GID `1000`。如果宿主用户不同，把 `id -u` 与 `id -g` 的结果写入 `.env` 的 `VID2NOTE_UID` 和 `VID2NOTE_GID` 后重新构建。不要把 `data/` 改成所有用户可写。

## 数据备份与恢复

停止写入后备份整个 `data/`：

```bash
docker compose stop
tar -czf vid2note-data-$(date +%Y%m%d).tar.gz data
docker compose start
```

恢复时停止容器，再恢复完整 `data/`。不要只复制 `tasks.db`，也不要只恢复 `credentials.enc` 而遗漏对应主密钥。
