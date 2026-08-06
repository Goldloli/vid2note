## Why

ASR 转录环节慢，是用户最明显的体感瓶颈。结合 社区 bcut 参考项目（`<workspace>/社区-bcut-参考项目`，同一套 bcut 协议）的对比调研与 vid2note 代码定位，根因有四：① 现状对 **bcut 在线路径也叠 VAD 分段**——2-3 小时视频被切成约 30 段、串行上传+轮询，而 bcut 服务器本身能处理长音频（社区 bcut 参考实现 即整段上传，不做 VAD），客户端分段纯属多余且放大了串行等待；② bcut 轮询间隔写死 `2s`、最大等待写死 `600s`，**未暴露到设置**，短任务端到端延迟偏高；③ bcut **无任何重试**，一次网络抖动即触发降级到慢得多的本地 whisper；④ **无文件级结果缓存**，同一份音频重复跑会重复整条上传+轮询（社区 bcut 参考实现 用 crc32 缓存解决了这点，是其唯一明显领先之处）。

社区 bcut 参考实现 的 bcut 实现协议与 vid2note 完全一致，但在 timeout、错误分类、降级、轮询 deadline 上**反而更弱**——这些 vid2note 已有的优势必须保留，不倒退。

## What Changes

- **bcut 在线走整段上传、不做 VAD 分段**：bcut 服务器处理长音频，客户端不再切段；VAD 切分 + 并行转录**仅保留给本地 whisper 路径**。若 bcut 对超大/超长文件返回上限错误，兜底退回 VAD 分段。
- **bcut 轮询改指数退避**：起步 1s、上限 8s（`min(base*2^n, 8) + 抖动`），替代固定 2s；并把 `query_interval`/`query_max_wait` 暴露到 `asr.config` 设置，可配。
- **bcut 加 `requests.Session` + `HTTPAdapter` 有限重试**：对 429/500/502/503/504 自动重试（有限次数 + 退避），避免单次抖动就降级；保留现有结构化 `AsrError` 与降级策略。
- **新增 crc32 文件级结果缓存**（借鉴 社区 bcut 参考实现 `BaseASR`）：同一份音频（字节级相同）命中缓存直接返回，跳过整条上传+轮询链路；缓存键 `{engine}-{crc32}-{lang}`。
- **`concurrency.max` 默认 `1` → `2`**：让本地 whisper 多段并行框架真正生效（在线 bcut 整段上传后不依赖此项）。

## Capabilities

### New Capabilities

无。全部落在既有 `speech-to-text` 之内。

### Modified Capabilities

- `speech-to-text`：
  - 长音频 VAD 分段策略改为**仅适用于本地引擎**；在线 bcut 走整段上传（遇上限错误兜底退回分段）。
  - 在线引擎降级前**先经有限重试**（429/5xx），重试用尽才降级。
  - `asr.config` 新增可配字段：`query_interval`、`query_max_wait`、缓存开关与目录；轮询改为指数退避。
  - 新增 crc32 文件级 ASR 结果缓存（同音频命中跳过上传+轮询）。

## Impact

- `backend/src/speech_to_text/bcut.py`：轮询改指数退避、`_BcutClient` 改用 `Session`+重试、新增整段上传入口与 crc32 缓存读写、`query_*` 参数从构造器接 `AsrConfig`。
- `backend/src/speech_to_text/pipeline.py`：`transcribe_audio` 在**在线引擎**路径跳过 VAD 分段、整段直传；本地引擎路径保留 VAD+`ThreadPoolExecutor` 并行。
- `backend/src/runtime/settings.py`：`concurrency.max` 默认值改 `2`；`asr.config` 默认补 `query_interval`/`query_max_wait`/缓存开关。
- `backend/src/speech_to_text/`（缓存模块）：新增轻量 crc32 缓存读写（存于 task work_dir 或 `data/`，JSON/SRT 序列化）。
- 测试：bcut 轮询退避、Session 重试、整段 vs 分段分流、crc32 命中/未命中；pipeline 在线整段、本地 VAD 分流。
- **保留不变**：每请求 `timeout`、结构化 `AsrError` 错误分类、轮询 deadline 检查、`online_first`/`single` 引擎选择策略、降级到本地 whisper。

## Non-goals

- 不改 bcut 协议本身（端点、model_id、分片上传协议不变）。
- 不做 bcut 分片**并发**上传（upload_urls 虽独立，但分片数通常很少，收益小；留后续）。
- 不做 faster_whisper 模型跨任务单例（架构改动，单独 change）。
- 不做流式/分块读取上传（大改，收益不在当前瓶颈）。
- 不改 ASR 引擎选择策略与降级目标（仍是 bcut 优先 → whisper 兜底）。
- 不改 SSE 实时日志机制（日志持久化是独立问题）。
