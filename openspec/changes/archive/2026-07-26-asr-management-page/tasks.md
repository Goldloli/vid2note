## 1. 后端 ASR 状态/测试接口

- [x] 1.1 新增 `backend/src/api/v1/asr.py`：`GET /asr/status`（三引擎就绪态，无副作用）+ `POST /asr/test {engine}`（连通性测试，返回 `{ok,latency_ms,message}`），接入 v1 路由（`api/v1/__init__.py`）
- [x] 1.2 `AsrConfig.asrtools_provider` 默认 `jianying`→`bcut`（dataclass + `from_settings`）；`TestAsr` 单测（status 三引擎 / bad engine 400 / whisper·external 未配置 ok=false）

## 2. 前端 ASR 管理页

- [x] 2.1 新增 `frontend/src/views/Asr.vue`：三引擎卡片（必剪云接口·在线免费 / Whisper 本地·离线CPU / 外部 ASR·自建HTTP）+ 适用场景
- [x] 2.2 默认引擎 + 策略选择（在线优先 / 指定单一），持久化 `asr.engine` / `asr.strategy`
- [x] 2.3 外部 endpoint + API Key 配置（写入 `asr.config`，含密钥脱敏提示，留空不覆盖）
- [x] 2.4 就绪态展示：`GET /asr/status` → 必剪 provider / whisper 模型 / external 配置
- [x] 2.5 连通性测试按钮：`POST /asr/test {engine}` → 展示 ok / latency_ms / message

## 3. 全站文案与设置联动

- [x] 3.1 新增 `frontend/src/asr.js` 统一文案常量；`Console.vue` / `Settings.vue` ASR 文案改「必剪云接口 / Whisper 本地 / 外部 ASR」
- [x] 3.2 `Settings.vue` 补 external 引擎 + 策略选择 +「在 ASR 页测试」跳转；修 ASR key 映射（`asr_engine`→`asr.engine`，load 取 `r.settings`）
- [x] 3.3 `App.vue` 侧栏 + `router/index.js` 加 ASR 入口（第 7 页，激活态高亮）
- [x] 3.4 `api/index.js` 加 `asrStatus()` / `asrTest(engine)`

## 4. 测试与验收

- [x] 4.1 后端 `TestAsr` 单测（status / test 各路径）；后端全量 239 测试绿
- [x] 4.2 `cd frontend && npm run build` 构建通过（Asr.vue 4.4kB 独立 chunk）
- [x] 4.3 联调：docker 内 `GET /asr/status`（provider=bcut / whisper 模型就绪）+ `POST /asr/test` 必剪云接口 `ok=true`(1762ms) 验证通过；浏览器 ASR 页交互待用户实测
- [x] 4.4 用 `bd` 建任务跟踪并随实现更新状态
