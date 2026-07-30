## Context

当前设置 API（`backend/src/api/v1/settings.py`）以 SQLite `settings` 表为唯一权威态，并把 `llm.credentials`、`asr.config`、`bilibili.cookie` 整体压成 `***`。这使 `frontend/src/views/Settings.vue` 与 `Asr.vue` 无法区分“未配置”和“已配置但不可编辑”，更无法实现按字段查看。现有 LLM 设置只保存当前 provider 的新输入，切换 provider 时还会清空编辑态。

LLM 运行栈通过 `backend/src/runtime/settings.py` 解析凭证，再由 `backend/src/llm/factory.py` 构造适配器。多数适配器虽然接受 `base_url`，却在设置 timeout 时重新创建写死地址的客户端；百度和 MiniMax 仍使用旧协议。笔记生成由 `SimpleProcessor` 调用既有 `generate_directly` / `generate_with_pdf_reference` prompt，适合在这一门面注入详细程度约束而不重写内核。

项目通过 `docker-compose.yml` 将仓库的 `./data` 映射到 `/app/data`，因此 `data/config/` 是同时满足“位于 compose 目录附近”“容器重建保留”和“不进入镜像”的最小持久化边界。

默认模型依据 2026-07-29 可访问的官方文档：

- DeepSeek `deepseek-v4-flash`：https://api-docs.deepseek.com/api/list-models
- Qwen `qwen3.7-plus`：https://help.aliyun.com/zh/model-studio/text-generation-model
- GLM `glm-5.2`：https://docs.bigmodel.cn/cn/guide/models/text/glm-5.2
- Kimi `kimi-k2.6`：https://platform.kimi.ai/docs/models
- 百度千帆 `ernie-5.0`：https://intl.cloud.baidu.com/en/doc/qianfan/s/7m95lyy43-intl-en
- 豆包 `doubao-seed-2-0-lite-260215`：https://www.volcengine.com/docs/82379/1795150
- MiniMax `MiniMax-M2.7`：https://platform.minimaxi.com/docs/api-reference/api-overview
- Ollama `qwen3.5`：https://ollama.com/library/qwen3.5

## Goals / Non-Goals

**Goals:**

- 以 ASRbox 的“页签 + 分组面板 + 状态徽标”信息架构细化设置和 ASR 页面，同时遵守 vid2note 的实色、无玻璃设计系统。
- 让 8 家内置 provider 和一个自定义 OpenAI 兼容槽位同时保存配置，且只有一个默认 provider。
- 让用户一眼分辨每个凭证字段是否已配置；默认隐藏，主动点击眼睛才按需读取明文。
- 把非敏感设置与任务数据库分离，并对全部敏感设置做认证加密。
- 让四档笔记详细程度成为任务创建时的稳定快照，并进入两条受维护的 prompt 路径。
- 升级当前模型默认值和已过时的百度、MiniMax 调用协议，连接测试真实验证所填 provider/model。

**Non-Goals:**

- 不引入账户、远程密钥服务、操作系统钥匙串或多用户权限模型。
- 不允许任意数量的自定义 provider；只维护一个 `custom` 槽位。
- 不动态覆盖用户模型 ID，也不把第三方模型列表可用性当作本地静态真相。
- 不改变已生成笔记；设置仍只影响后续任务。
- 不为笔记详细度建立四套完全重复的 prompt 文件。

## Decisions

### 1. 设置权威态拆为 JSON 设置与加密凭证

新增 `SettingsStore`，默认目录为 `${DATA_ROOT}/config`：

```text
data/config/
├─ settings.json       # 非敏感、可读、原子写入
├─ credentials.enc     # Fernet 认证加密后的 JSON
└─ master.key          # 仅缺少外部主密钥时生成，0600
```

`settings.json` 保存扁平设置和 provider 的非敏感字段（模型、Base URL、自定义名称）；`credentials.enc` 保存 LLM API Key、ASR 外部 API Key 和 Bilibili cookie。写入采用同目录临时文件、`fsync`、`os.replace`，避免断电得到半个 JSON。

主密钥优先级：

1. `VID2NOTE_MASTER_KEY`
2. `VID2NOTE_MASTER_KEY_FILE`（默认探测 `/run/secrets/vid2note_master_key`）
3. 自动生成 `${DATA_ROOT}/config/master.key` 并强制 `0600`

选择 Fernet 而不是自制 AES 格式，因为它同时提供加密、完整性校验和成熟的密钥编码。把主密钥与密文都放在 `./data` 只能防止单独分享配置文件时泄密，不能防止整个宿主目录被窃取；高安全用户应使用环境变量或 Docker secret。

备选方案：

- 仅让 `settings.json` 排除密钥、密钥继续明文留 SQLite：实现简单，但无法满足密钥落盘加密。
- 把密钥写入 `.env`：不适合 UI 动态更新，并容易被误提交。
- 系统钥匙串：Docker/Linux/群晖等部署不可移植，本次不采用。

### 2. 普通状态与明文读取分离

普通 `GET /api/v1/settings` 不返回任何明文，只返回：

```json
{
  "credentials": {
    "deepseek": {
      "api_key": {
        "configured": true,
        "masked": "••••••••a1b2"
      }
    }
  }
}
```

新增字段白名单接口 `POST /api/v1/settings/credentials/reveal`，请求 `{provider, field}`，响应只含该字段明文并设置 `Cache-Control: no-store`。前端仅在眼睛按钮点击时调用，离开 provider/页签或 60 秒后从内存清除并重新隐藏。清除凭证使用显式 DELETE/clear 语义，空输入不覆盖旧值。

应用仍只监听 localhost、保持同源且无宽松 CORS。该模型不能抵御本机恶意软件或浏览器扩展，但避免了普通页面加载、日志、缓存和错误响应中的被动泄露。

### 3. Provider 注册表是前后端共享契约

后端维护 provider 元数据：ID、显示名、默认模型、默认 Base URL、字段清单、是否本地、是否需要密钥。前端通过设置 API 获取，不再各自硬编码一套。内置 provider 为：

| Provider | 默认模型 | 凭证 |
| --- | --- | --- |
| deepseek | `deepseek-v4-flash` | API Key |
| qwen | `qwen3.7-plus` | API Key |
| glm | `glm-5.2` | API Key |
| moonshot | `kimi-k2.6` | API Key |
| baidu | `ernie-5.0` | API Key |
| doubao | `doubao-seed-2-0-lite-260215` | API Key |
| minimax | `MiniMax-M2.7` | API Key |
| ollama | `qwen3.5` | 无必需密钥 |
| custom | 空（必填） | 可选 API Key |

模型输入为带建议值的普通文本框，不是封闭下拉框。自定义槽位使用 OpenAI Chat Completions 兼容协议，要求名称、Base URL 和模型 ID。

连接测试会发送最小对话请求验证 URL、鉴权和模型，可能产生极少量费用，页面必须明确提示。适配器保存并复用实际 `base_url`；设置 timeout 时不得回退硬编码地址。百度迁移到千帆 v2 Bearer API Key，MiniMax 迁移到当前 OpenAI 兼容 v1，不再要求旧 `secret_key` / `group_id`。

### 4. 页签职责保持单一

设置中心页签：

- 通用：界面语言、背景
- LLM 服务：provider 卡片、默认 provider、模型、URL、密钥状态、测试
- 笔记生成：输出语言、详细程度、截图、图片质量、PDF 模式
- 存储与清理：总量/分类统计、五类保留策略
- 高级设置：并发、chunk size、temperature、重试
- 关于：版本、运行模式、配置文件路径

ASR 页面保留侧栏入口，并使用内部页签：

- 引擎：三引擎卡片、默认选择和状态
- Whisper 本地：模型路径、binary、语言、device/compute type 只读说明
- 外部 ASR：endpoint、API Key、超时
- 转录策略：在线优先/单一、VAD 阈值、分段并发

设置页只显示 ASR 摘要和前往 ASR 的入口，不提供第二份可编辑表单。

### 5. 笔记详细程度映射为附加约束

新增 `note.detail_level`，合法值：

- `concise`：只保留结论、核心概念、关键数据和必要步骤
- `balanced`：默认；保留主要论点、解释、示例和结论
- `detailed`：补充推导、上下文、例子、注意事项和章节小结
- `exhaustive`：尽量完整覆盖有效信息，保留推导链、例子、反例、边界和术语说明

实现使用一份受测试的 detail 指令映射，插入现有 `generate_directly` 与 `generate_with_pdf_reference` 模板；不复制整套 prompt。档位只控制内容覆盖率，不允许捏造字幕或讲义中不存在的信息。任务创建时保存档位快照，重跑沿用原任务档位。

### 6. 一次性迁移与回滚

首次启动若没有 `settings.json`：

1. 读取 SQLite `settings` 表和环境变量形成旧快照。
2. 拆分非敏感设置与凭证。
3. 原子写入 JSON 和加密文件，再重新读取/解密验证。
4. 写入迁移版本标记。
5. 删除 SQLite 中已迁移的敏感值；非敏感旧值保留供旧版本回滚，但新版本不再读取。

如果任一步失败，继续使用旧 SQLite 路径并报告错误，不删除旧值。回滚旧镜像时非敏感设置仍可读取；凭证需要从备份恢复主密钥和密文，或在旧设置页重新填写。

## Risks / Trade-offs

- [自动生成的主密钥与密文同属 `./data`] → 文档明确其只防误分享；支持环境变量/Docker secret，并在关于页显示当前密钥来源级别。
- [明文 reveal 接口扩大本机攻击面] → localhost + 同源、字段白名单、no-store、无日志、前端自动清除；普通 GET 永不返回明文。
- [厂商模型持续更新或下线] → 默认值来自带日期的官方调研；模型框始终可编辑，不自动改写用户配置。
- [真实连接测试会产生费用和外部请求] → 只在用户主动点击时执行，使用最小 token，并在 UI 前置说明。
- [迁移中断造成配置损坏] → 双文件原子写、写后校验、成功前不删旧值。
- [部分新模型限制 temperature] → provider 适配器对已知固定参数模型省略不兼容采样字段；全局 temperature 仅在服务支持时传递。

## Migration Plan

1. 先加入存储/加密/迁移单元测试与 API 契约测试。
2. 实现外置设置服务并保持旧 API 响应兼容，完成一次性迁移。
3. 更新 provider 注册表、适配器、默认模型和连接测试。
4. 加入笔记详细程度设置、任务快照和 prompt 测试。
5. 重构设置与 ASR 页面并完成响应式、键盘和密钥交互测试。
6. 更新 compose、`.env.example`、用户文档和配置路径说明。
7. 重建容器，以现有数据库验证迁移；保留迁移前数据库和 `data/config` 备份。

## Open Questions

无。用户已确认明文按需查看、8 家与自定义配置、独立 ASR 页面、页签范围和四档详细程度。
