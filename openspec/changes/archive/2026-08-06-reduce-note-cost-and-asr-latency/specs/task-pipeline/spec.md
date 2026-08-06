## ADDED Requirements

### Requirement: ASR 性能指标持久化

ASR 节点 MUST 在不改变顶层 `srt_path` 的前提下，把 JSON-safe 性能指标写入该节点 product metadata。至少 MUST 包含缓存命中、音频时长、分段数、worker 数、源字节、上传字节、切分耗时、转录耗时和总耗时；失败任务 SHALL 保留已获得的阶段指标。历史任务没有 metadata 时 MUST 继续可读。

#### Scenario: 冷启动任务记录分段指标
- **WHEN** 长音频完成 bcut 冷启动转录
- **THEN** 任务详情的 ASR 节点 product MUST 含 `cache_hit=false`、非零分段数、worker 数、上传字节和各阶段秒数

#### Scenario: 热缓存任务记录命中
- **WHEN** ASR 在 VAD 前命中整段缓存
- **THEN** product MUST 含 `cache_hit=true`、`segment_count=0`、`upload_bytes=0` 和缓存查找/总耗时

#### Scenario: 历史 product 向后兼容
- **WHEN** 读取一个只有 path 和 size_bytes 的历史 ASR 节点
- **THEN** API 和前端 MUST 正常展示既有产物，MUST NOT 因 metadata 缺失报错
