## 1. bcut 引擎：轮询退避 + Session 重试

- [x] 1.1 `_BcutClient` 改用 `requests.Session`（连接复用）+ `HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[429,500,502,503,504], allowed_methods=["GET","PUT","POST"]))`，所有 `post/put/get` 走 session
- [x] 1.2 轮询改指数退避：`min(base*2**n, 8) + random.uniform(0,0.3)`，替代固定 `time.sleep(query_interval)`；保留 deadline 检查
- [x] 1.3 `BcutEngine.__init__` 从 `AsrConfig` 接 `query_interval`/`query_max_wait`（而非写死 2.0/600.0）；`build_engines` 透传（`pipeline.py:151-153`）

## 2. crc32 文件级结果缓存（借鉴 社区 bcut 参考实现 BaseASR）

- [x] 2.1 新增缓存模块（`speech_to_text/asr_cache.py`）：键 `{engine}-{crc32(audio_bytes)}-{lang}`，缓存目录 `data/asr_cache/`，值为序列化 cues（JSON）；提供 `get(key)`/`put(key, cues)`/文件读写
- [x] 2.2 `BcutEngine.transcribe`（及通用入口）先算 crc32 查缓存，命中直接解析返回 cues、跳过上传+轮询；未命中正常转录后 `put`
- [x] 2.3 缓存开关 `cache_enabled`（默认 True）从 `AsrConfig` 接入；关闭时不读写缓存

## 3. pipeline 分流：在线整段 vs 本地 VAD

- [x] 3.1 `transcribe_audio`（`pipeline.py:340-395`）判断引擎类别：在线引擎（bcut/external）跳过 VAD 分段、整段调引擎；本地引擎（whisper.cpp）走现有 VAD 切分 + `_transcribe_segments_parallel`
- [x] 3.2 在线整段上传若返回文件大小/时长上限错误（识别特定 state/HTTP），兜底退回 VAD 分段（复用 `_transcribe_segments_parallel`），MUST NOT 静默失败
- [x] 3.3 `concurrency`（`pipeline.py:95`）默认改 2（`AsrConfig` 与 `concurrency.max` 回退读取处同步）

## 4. 设置：默认值与 asr.config 字段

- [x] 4.1 `runtime/settings.py` `concurrency.max` 默认值 `1` → `2`（`MAX_CONCURRENCY` 仍 3）
- [x] 4.2 `AsrConfig.from_settings`（`pipeline.py:99-140`）解析新字段：`query_interval`（默认 1.0）、`query_max_wait`（默认 600.0）、`cache_enabled`（默认 True）、`cache_dir`
- [x] 4.3 ASR 设置页（前端 + 后端校验）暴露 `query_interval`/`query_max_wait`/`cache_enabled`，数值范围与布尔白名单校验（复用现有 ASR 配置校验路径）

## 5. 测试与校验

- [x] 5.1 bcut 单测：轮询指数退避节奏、`Session`+`Retry` 对 429/5xx 重试、重试用尽抛 `AsrError`；保留 timeout/错误分类/deadline 不回归
- [x] 5.2 crc32 缓存单测：命中跳过上传、不同音频不命中、关闭开关不读写
- [x] 5.3 pipeline 分流单测：在线引擎整段调一次（不分段）、本地引擎走 VAD 分段、在线整段上限错误兜底退回分段
- [x] 5.4 `openspec validate optimize-asr-throughput --strict` 通过；`cd backend && .venv/bin/python -m pytest` 全绿
- [x] 5.5 docker 重建后跑真实长音频任务验证：在线整段上传（不再切 30 段）、重复音频二次命中缓存秒返回、延迟显著下降
