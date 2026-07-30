## 1. 采集与上报

- [x] 1.1 `openai_compatible.py`：新增 `normalize_usage`，`chat()` 记录 `self.last_usage`（含 DeepSeek / OpenAI 缓存字段映射与缺失补 0）
- [x] 1.2 `SimpleProcessor`：config 支持 `usage_callback`，`_call_llm` 调用后按 `operation_name` 上报，回调异常不中断生成
- [x] 1.3 单测：usage 归一化（DeepSeek 字段 / OpenAI cached_tokens / 无 usage / 无缓存字段）、`_call_llm` 上报与 mock 无属性降级

## 2. 聚合与落库

- [x] 2.1 `runner.py`：新增 `classify_llm_operation` 与 `LlmUsageAggregator`，`_note` / `_mindmap` 共享实例并在节点结束后 `repo.update(task_id, llm_usage=...)`
- [x] 2.2 持久化：tasks 表增量迁移加 `llm_usage` 列，同步 `models/task.py` 与 `task_repository.py`
- [x] 2.3 单测：阶段分类映射、聚合器两级累计与 `to_dict` 结构、仓库 create/update 往返、旧库 ALTER 迁移

## 3. API 与前端

- [x] 3.1 任务详情响应含 `llm_usage` 的 API 测试
- [x] 3.2 `TaskDetail.vue` 新增「LLM 消耗」区块（分阶段表格 + 总计 + 命中率，无数据不显示）
- [x] 3.3 中英文案与前端单测（有数据渲染 / 空数据隐藏 / 命中率计算）

## 4. 质量门禁与验证

- [x] 4.1 `openspec validate add-llm-usage-observability --strict` 与后端完整 pytest
- [x] 4.2 前端 Node 测试、lint 与生产构建
- [x] 4.3 重建 Docker，用真实超详细任务验证详情页展示与 DeepSeek 命中/未命中拆分
