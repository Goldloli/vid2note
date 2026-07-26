## Context

ASR 后端能力已齐全：`AsrConfig`（`pipeline.py`）含三引擎 + 策略 + `asrtools_provider`（jianying/bcut）+ external endpoint/key + whisper 模型路径，`AsrConfig.from_settings` 从 `asr.engine` / `asr.strategy` / `asr.config`(JSON) 构造，`build_engines` 按策略编排降级。但前端只暴露两个裸引擎，无 external / 策略 / 就绪态 / 测试，且 Settings 的 `asr_engine`（下划线）与后端 `asr.engine`（点号）key 不匹配导致选择**存不进**。本 change 把已有后端能力完整暴露到前端，并新增轻量 `status` / `test` 接口。

## Goals / Non-Goals

**Goals:** 独立 ASR 页（三引擎说明 + 策略 + external + 就绪态 + 连通性测试）；全站文案友好化（在线 ASR 称「必剪云接口」）；Settings 补 external + 策略 + 修 key 映射；默认 provider `bcut`。

**Non-Goals:** 真实音频试转；改三引擎转录核心；Console 上传/统计/SSE、History、TaskDetail（change ③）。

## Decisions

### D1 独立 ASR 页（侧栏第 7 入口）

- **Why**：ASR 信息密度高（说明 + 策略 + 就绪态 + 测试），独立页比塞进 Settings 清晰、发现性好；spec 原导航 6 页 → 加 ASR 成 7 页（修订「应用骨架与导航」Requirement）。
- **Alt**：全塞 Settings（拥挤）、抽屉/弹层（发现性差）。

### D2 `GET /asr/status` 就绪态（无副作用，秒回）

- 读 settings 快照 + 文件系统检查。返回：
  - `asrtools`: `{available: true, provider: 'bcut'}`（在线引擎恒可用，不探活）
  - `whisper_cpp`: `{available, model_exists, binary_exists}`（`available = model_path 文件存在`）
  - `external`: `{available, endpoint_configured}`（`available = endpoint 非空`）

### D3 `POST /asr/test {engine}` 连通性测试（非真实转录）

- `asrtools`：对 `asrtools_sign_endpoint` 发轻量 GET 探活（短 timeout），返回可达性 + 耗时；不传音频。
- `whisper_cpp`：检查 binary 可执行（`--help` 退出码 0 或存在性）+ model 文件可读。
- `external`：对 endpoint 发 GET/HEAD 探活（带 api_key，短 timeout）。
- 统一返回 `{ok, latency_ms, message}`。**不做真实音频转录**（v1 边界，见 Non-goals）。

### D4 默认 provider `bcut` + 文案「必剪云接口」

- `AsrConfig.asrtools_provider` 默认 `jianying` → `bcut`；`DEFAULT_SETTINGS["asr.config"]` 同步；全站文案统一「必剪云接口（在线·免费）」。用户 2026-07-26 确认走必剪免费接口。

### D5 Settings key 映射修复

- 前端 Settings 把 `asr_engine` / `asr_strategy` 映射为后端 `asr.engine` / `asr.strategy`；`external` endpoint + key 写入 `asr.config`(JSON)。修复「选了存不进」的 bug。

## Risks / Trade-offs

- **[sign endpoint 探活被限流 / 无 GET 支持]** → 短 timeout（≤8s），失败返回明确 message，不阻塞页面。
- **[whisper binary 容器内可能未装]** → 仅检查存在性，缺失返回「未安装（容器未内置 whisper.cpp）」，不报错。
- **[改默认 provider 影响存量]** → 仅影响无显式 `asr.config` 的新任务；存量 settings 不动。

## Migration Plan

前端增量 + 后端新增路由，无数据迁移。默认 provider 改动仅影响无显式配置的新任务。回滚：移除 `Asr.vue` / `asr.py` + 还原文案常量。
