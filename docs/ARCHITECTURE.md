# 架构与扩展点

## 总览

vid2note 使用单容器、同源架构：

```text
Browser
  │
  ├── Vue 3 static assets
  └── /api/v1
        │
        ▼
     FastAPI
        │
        ├── TaskService ── SQLite
        ├── SettingsStore ── settings.json
        ├── CredentialStore ── Fernet ciphertext
        ├── RuntimeWorker
        └── DagRunner
              ├── download
              ├── extract_audio
              ├── asr
              ├── note
              ├── mindmap
              └── cleanup
```

任务状态变化先写入 SQLite，再发布 SSE。容器重启时，遗留的 `running` 任务会标记为失败，用户可从失败节点重跑。

## 目录职责

- `backend/src/api/v1/`：对外 HTTP/SSE 接口。
- `backend/src/runtime/`：任务服务、Worker、DAG 执行入口和设置快照。
- `backend/src/runtime/settings_store.py`：版本化公开设置、原子写入、last-good 副本、加密凭证和旧库迁移。
- `backend/src/pipeline/`：与业务无关的 DAG 状态机。
- `backend/src/media_ingest/`：来源识别、yt-dlp 下载和 FFmpeg 音频提取。
- `backend/src/speech_to_text/`：ASR 抽象、三种引擎和 VAD。
- `backend/src/llm/`：LLM 统一接口和 Provider 工厂。
- `backend/src/core/kernel/`：从 `ai_srt2md` 继承的稳定门面。
- `backend/src/retention/`：产物保留和临时目录清理。
- `frontend/src/`：同源 Web UI。

## 数据流

1. API 校验 URL 或流式保存上传文件。
2. `TaskService` 固化任务配置快照并入队。
3. `RuntimeWorker` 按配置并发度消费队列。
4. `DagRunner` 驱动节点状态；每个节点只读上游产物、登记自己的产物。
5. Repository 持久化权威状态，SSE 总线向浏览器推送事件。
6. Retention 根据五类产物策略回收文件。

## 新增 LLM Provider

1. 在 `backend/src/llm/` 实现 `BaseLLM.chat()`。
2. 在 `LLMFactory` 注册 Provider。
3. 在 `llm/provider_registry.py` 注册名称、默认模型、默认地址和凭证字段。
4. 在 `LLMFactory` 和 `llm/__init__.py` 注册实现。
5. 增加工厂、环境变量、连接测试和任务模型选择测试。
6. 更新 `.env.example`、前端文案和配置文档。

OpenAI-compatible 服务复用 `backend/src/llm/openai_compatible.py`；无需新增代码的私人 endpoint 可直接使用“自定义兼容服务”槽位。

## 设置与凭证数据流

1. `GET /api/v1/settings` 合并公开设置、环境默认值和 Provider 注册表，只返回凭证状态与脱敏摘要。
2. `PUT /api/v1/settings` 先在内存中校验完整候选对象，再原子替换 `settings.json` 和 last-good 副本。
3. 凭证接口按 namespace、Provider、field 白名单读写 `credentials.enc`，普通设置接口拒绝敏感键。
4. 运行任务时先读取任务固化的 Provider / 模型 / 详细度，再从加密仓库或环境变量解析凭证。
5. 旧 SQLite 设置只作为一次性迁移源和迁移失败时的回落，不再是公开设置权威态。

## 新增 ASR Engine

实现 `AsrEngine.transcribe()`，统一返回 `list[Cue]`，并使用 `AsrError` 的结构化原因。然后在：

- `speech_to_text/pipeline.py` 注册构造和策略顺序；
- `runtime/settings.py` 注册枚举；
- `/api/v1/asr` 提供无副作用的就绪检查；
- `frontend/src/asr.js` 注册界面名称；
- 测试降级、取消、空音频和时间戳单调性。

## 安全边界

- 应用无认证，因此默认网络边界是 localhost。
- 下载 URL、上传文件、产物路径和 Markdown HTML 都是不可信输入。
- Provider 凭证不得写入日志或 API 响应。
- 明文 reveal 必须是单字段、显式操作、禁止缓存，且前端应自动重新隐藏。
- `data/` 是用户隐私边界，不属于可分享的诊断包。

更多规则见 [SECURITY.md](../SECURITY.md)。
