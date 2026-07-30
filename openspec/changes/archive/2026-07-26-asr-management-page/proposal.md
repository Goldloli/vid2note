## Why

ASR 是 vid2note 的核心能力，但前端对它的暴露非常初级：Console 只有两个裸名 chip（`bcut`/`whisper_cpp`）、Settings 文案直接暴露内部在线实现名、**漏了 `external` 第三引擎**与「在线优先·失败转本地 / 指定单一」策略；用户无从知晓各引擎差异、whisper 模型是否就绪、在线接口是否可达。此外 Settings 的 ASR 选择因 key 名不匹配（前端 `asr_engine` vs 后端 `asr.engine`）实际**存不进去**。本 change 新增独立 ASR 管理页，统一三引擎说明（实验性在线 ASR 对外称「bcut」）、暴露策略与 external、提供就绪态与连通性测试，并全站替换为友好文案。

## What Changes

- **新增独立「ASR」页**（侧栏新增第 7 个入口）：
  - 三引擎卡片：**bcut**（在线·实验性）/ **Whisper 本地**（离线·CPU）/ **外部 ASR**（自建 HTTP），各含说明与适用场景。
  - 默认引擎 + **策略**（在线优先·失败转本地 / 指定单一）选择，持久化到 settings（修 key 名映射 bug）。
  - `external` endpoint + api_key 配置（此前前端完全没暴露）。
  - 各引擎**就绪态**：whisper 模型文件 / binary 是否就绪、external 是否已配置、bcut provider。
  - **连通性测试**按钮：验证引擎可达 / 模型可加载，返回成功失败 + 耗时。
- **全站 ASR 文案友好化**：`Console.vue` / `Settings.vue` 用「bcut」「Whisper 本地」「外部 ASR」替代裸名 / 技术名。
- **Settings ASR 区**：补 `external` 引擎 + 策略选择 +「在 ASR 页测试」跳转。
- **默认在线 ASR 改为 `bcut`**，文案统一为中性的「bcut」。
- **后端新增** `GET /api/v1/asr/status`（就绪态，无副作用）+ `POST /api/v1/asr/test`（连通性测试）。

## Capabilities

### New Capabilities

（无 —— 不引入新 capability。）

### Modified Capabilities

- `web-frontend`：**新增「ASR 管理页」Requirement**；修订「应用骨架与六页导航」→ **七页**（侧栏 +ASR）；修订「设置页 ASR 与 LLM 引擎配置」（补 external + 策略 + 跳转测试 + 修 key 映射）。
- `speech-to-text`：实验性在线 ASR 的对外措辞调整为「bcut」；默认 provider `bcut`。

## Impact

- **前端**：新增 `frontend/src/views/Asr.vue`；改 `App.vue`（侧栏 + 路由第 7 入口）、`router/index.js`、`Console.vue`（文案 + external + 策略 chip）、`Settings.vue`（文案 + external + 策略 + 修 key 映射 + 跳测试）、`api/index.js`（+asrStatus/asrTest）。
- **后端**：新增 `backend/src/api/v1/asr.py`（`status` + `test`）；改 `AsrConfig` 与 settings 的默认引擎为 `bcut`；接入 v1 路由。
- **spec**：`web-frontend`（+ASR 页 / 修订导航 + 设置）、`speech-to-text`（描述措辞 + 默认 provider）。
- **测试**：后端 `asr status/test` 单测；前端 `npm run build`。

## Non-goals

- **不做真实音频试转**：v1 的测试为「连通性测试」（探活 / 模型可加载），不实际转录音频；真实试转留后续版本。
- 不改三引擎的转录核心实现（bcut / whisper.cpp / external 的转写逻辑不变）。
- 不改 Console 的本地上传 / 统计卡 / SSE、History、TaskDetail（归属 change ③）。

### 复用 vs 新增边界

- **复用**：`AsrConfig.from_settings`、`build_engines`、settings 读写 API、`DESIGN.md` 卡片 / chip 组件。
- **新增 / 改造**：`Asr.vue`、后端 `asr.py`（status/test）、文案常量、默认 provider、Settings key 映射修复。
