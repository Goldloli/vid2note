# 监控与性能

## 关键指标

| 指标 | 目标 | 说明 |
|------|------|------|
| TTFT | < 1s | LLM 首 token 返回时间 |
| 检索延迟 | < 200ms | 向量搜索 |
| 节点超时 | 5-15min | 按节点类型设置 |
| 并发任务 | 3 | 默认 worker 数 |

## 日志

- 结构化 JSON 日志
- 按 task_id 分文件：`logs/task_{id}.log`
- 级别：debug/info/warning/error

## 错误码

| 代码 | 含义 | 重试策略 |
|------|------|----------|
| DOWNLOAD_URL_INVALID | URL 无效 | 不重试 |
| DOWNLOAD_COOKIE_EXPIRED | Cookie 过期 | 人工处理 |
| ASR_TOOL_B_CHANGED | 第三方工具变更 | 升级适配器 |
| LLM_RATE_LIMITED | 限流 | 指数退避 |
| PIPELINE_NODE_TIMEOUT | 节点超时 | 可重试 |

## 性能优化建议

1. **ASR**: 优先使用本地 GPU（FunASR）降低延迟和成本
2. **LLM**: 使用流式输出减少等待感
3. **下载**: 开启 yt-dlp 缓存避免重复下载
4. **音频**: 提取时直接降采样到 16kHz

## 告警

- Sentry 集成（可选）
- 任务失败率 > 10% 触发告警
- 磁盘使用率 > 80% 触发告警
