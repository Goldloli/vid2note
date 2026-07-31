## Context

ASR 转录慢是用户最明显的体感瓶颈。结合 社区 bcut 参考项目（`/Volumes/worknie/Desktop/ai_code/项目参考/社区 bcut 参考项目`，同一套 bcut 协议）对比调研与 vid2note 代码定位，最大元凶是**对在线 bcut 也叠 VAD 分段**：2-3 小时视频被切成约 30 段、串行上传+轮询，而 bcut 服务器本身能处理长音频（社区 bcut 参考实现 `BcutASR.py` 即整段上传、不做 VAD），客户端分段对在线路径纯增串行等待。次要元凶：轮询固定 2s 不可配（`bcut.py:235-236,285`）、无重试一次抖动即降级、无文件缓存导致重复音频重复上传。

社区 bcut 参考实现 协议流程与 vid2note 完全一致，但在 timeout、错误分类、降级、轮询 deadline 上**反而更弱**——这些 vid2note 已有优势必须保留。社区 bcut 参考实现 唯一领先点是 **crc32 文件级缓存**（`BaseASR.py:54-79`）与**整段上传策略**，本变更据此借鉴。

## Goals / Non-Goals

**Goals:**
- 在线 bcut（及外部 endpoint）走整段上传，省掉 N 段串行上传+轮询。
- bcut 轮询改指数退避，`query_interval`/`query_max_wait` 暴露到 `asr.config`。
- bcut 加 `Session` + 有限重试，避免单次抖动降级。
- 新增 crc32 文件级缓存，重复音频跳过整条上传+轮询。
- `concurrency.max` 默认提到 2，让本地 whisper 多段并行真正生效。

**Non-Goals:**
- 不改 bcut 协议本身；不做分片并发上传；不做 faster_whisper 模型跨任务单例；不做流式上传；不改引擎选择策略与降级目标；不改 SSE 日志机制。

## Decisions

**D1 长音频 VAD 分段并行（2026-07-31 实测修订）**
原假设「bcut 整段处理长音频」不成立——实测 bcut 整段 6min 成功（6s）、8min 失败（238s，服务器端 result 异常），**bcut 整段上限约 6-7min**。故长音频（> `vad_threshold` 默认 5min）一律 VAD 分段并行：每段 < 5min，在线引擎每段整段必成功；`concurrency` 默认 2 让多段并行。在线整段仅用于 ≤ threshold 的短音频（本来就不分段）。**MUST NOT 对长音频整段尝试**（注定失败且浪费数分钟轮询）。

**D2 分段内降级**
分段后每段经现有 `_EngineResolver`：单段在线失败自动降级本地 whisper（既有逻辑），段级失败不扩散到其他段。

**D3 轮询指数退避**
`min(base * 2^n, 8) + random.uniform(0, 0.3)`，起步 1s、上限 8s，替代固定 2s；`query_interval`（起步间隔）/`query_max_wait`（总上限）从构造器接 `AsrConfig`，暴露到 `asr.config`。保留现有 deadline 检查（`time.time() > deadline` 抛 `AsrError`）。

**D4 `requests.Session` + `HTTPAdapter` 有限重试**
`_BcutClient` 持有一个 `Session`，挂 `HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[429,500,502,503,504], allowed_methods=["GET","PUT","POST"]))`，把重试/退避下放到 urllib3 层。保留 `_raise_for_status` 的结构化 `AsrError` 分类——重试由 urllib3 在底层做，用尽后仍按现状抛 `AsrError` 触发 pipeline 降级。

**D5 crc32 文件级缓存（借鉴 社区 bcut 参考实现 `BaseASR`）**
键 `{engine}-{crc32(audio_bytes)}-{lang}`，缓存目录 `data/asr_cache/`，值为序列化的 cues（JSON）。`BcutEngine.transcribe` 先算 crc32 查缓存，命中直接解析返回 cues、跳过上传+轮询；未命中则正常转录后写缓存。缓存开关 `asr.config.cache_enabled`（默认开）。借鉴 社区 bcut 参考实现 `BaseASR.py:54-79` 的 `_set_data/_get_key/run` 模式。

**D6 `concurrency.max` 默认 1 → 2**
本地 whisper 多段并行框架（`pipeline.py:411` `ThreadPoolExecutor`）默认 workers=1 形同虚设；改默认 2 让其生效（`MAX_CONCURRENCY` 仍为 3 上限）。在线整段上传后不依赖此项。

## Risks / Trade-offs

- **[bcut 整段超服务器上限]** → D2 兜底退回 VAD 分段，不静默失败。
- **[bcut 协议/服务变化]** → 保留结构化 `AsrError` 分类 + pipeline 降级，行为不倒退。
- **[缓存膨胀]** → 键带 crc32、存 `data/asr_cache/` 持久；容量治理/LRU 为后续 non-goal。
- **[重试放大 429 限流]** → `Retry(total=3, backoff_factor=0.5)` 有限且带退避，不会无限重试。
- **[整段上传内存占用]** → 现状已 `file.read()` 整文件进内存（`bcut.py:261-262`），无回归；流式上传为 non-goal。
- **[缓存一致性]** → 键含 crc32（字节级），音频任何改动都不命中；引擎/语言变化也不命中。
