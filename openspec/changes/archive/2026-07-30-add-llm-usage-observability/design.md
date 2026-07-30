# 设计：LLM 用量观测

## 1. 采集层（adapter）

`OpenAICompatibleLLM.chat()`（`backend/src/llm/openai_compatible.py`）在拿到 `response` 后、返回前执行：

```python
self.last_usage = normalize_usage(getattr(response, "usage", None))
```

`normalize_usage` 产出纯 dict，字段固定：

```python
{
    "prompt_tokens": int,
    "completion_tokens": int,
    "cache_hit_tokens": int,    # DeepSeek prompt_cache_hit_tokens
                                # 或 OpenAI usage.prompt_tokens_details.cached_tokens
    "cache_miss_tokens": int,   # DeepSeek prompt_cache_miss_tokens；
                                # 无该字段时 = prompt_tokens - cache_hit_tokens
}
```

- 不改 `chat()` 返回签名（仍为 `str`），所有既有调用方与 `MockLLM` 不受影响；mock / Ollama 没有 `last_usage` 属性时下游用 `getattr(llm, "last_usage", None)` 安全降级。
- `last_usage` 是「最近一次调用」语义，消费方必须在每次 `chat()` 返回后立即读取（`_call_llm` 天然满足，全部调用串行）。

## 2. 上报层（SimpleProcessor）

`SimpleProcessor.__init__` 从 config 读可选 `usage_callback`（与 `progress_callback` 同一注入方式）。`_call_llm` 在 `self.llm.chat(...)` 成功后：

```python
usage = getattr(self.llm, "last_usage", None)
if self.usage_callback is not None and usage:
    self.usage_callback(operation_name, usage)
```

回调异常只记日志、不中断生成（同 progress_callback 的容错语义）。

## 3. 聚合与落库（runner）

`runner.py` 新增模块级纯函数与聚合器：

- `classify_llm_operation(operation_name) -> str`：把操作名映射为阶段键——
  `understand`（超详细字幕理解/证据 ID 修复）、`blueprint`（蓝图及修复）、`draft`（章节初稿）、`review`（章节审校/格式修复/术语保真）、`mindmap`（思维导图大纲）、`other`（PDF 结构分析、普通笔记生成等）。
- `LlmUsageAggregator`：`record(operation_name, usage)` 累计 `by_operation` 与 `by_stage` 两级；`to_dict()` 产出落库结构。

`_note` 与 `_mindmap` 执行器从 `ctx` 共享同一个聚合器实例（runner 在 `_make_executors` 作用域创建），各自注入 `usage_callback=aggregator.record`。两个节点结束后 `repo.update(task_id, llm_usage=aggregator.to_dict())`（runner 已有 `repo.update` 更新 title 的先例）。

落库 JSON 结构（存 tasks.llm_usage TEXT 列）：

```json
{
  "total": {"calls": 23, "prompt_tokens": 3200000, "completion_tokens": 620000,
            "cache_hit_tokens": 400000, "cache_miss_tokens": 2800000},
  "by_stage": {
    "understand": {"calls": 5, "prompt_tokens": ..., "completion_tokens": ...,
                   "cache_hit_tokens": ..., "cache_miss_tokens": ...},
    "blueprint": {...}, "draft": {...}, "review": {...}, "mindmap": {...}, "other": {...}
  },
  "by_operation": {
    "超详细字幕理解(1/5)": {"stage": "understand", "calls": 1, ...}
  }
}
```

## 4. 持久化

照 `note_detail_level` 的增量迁移范式（`database.py` `_migrate_db` 的 elif 分支）：

```sql
ALTER TABLE tasks ADD COLUMN llm_usage TEXT NOT NULL DEFAULT '{}'
```

同步更新：`models/task.py`（`JSON_DICT_FIELDS`、dataclass 字段、`to_dict`、`from_dict`、`from_db_row`）、`db/task_repository.py`（`_JSON_COLUMNS`、INSERT）。任务详情 API 经 `to_dict()` 零改动透出。

## 5. 前端展示

`TaskDetail.vue` 在 `detail-grid` 之后新增 `<section class="surface">`（仅当 `task.llm_usage?.total?.calls > 0` 时渲染）：

- `SectionHeader`：标题「LLM 消耗」+ 描述（含命中率说明）
- 表格：行 = 有调用的阶段（顺序固定 understand→blueprint→draft→review→mindmap→other）+ 总计行；列 = 阶段 / 调用次数 / 输入 tokens / 缓存命中 / 未命中 / 输出 tokens / 输入命中率
- 样式复用现有 token（`--border/--muted/--mono`），数字右对齐、tabular-nums，遵循 DESIGN.md（实色卡片、无渐变）
- 中英文案进 `locales/zh.js` / `en.js`

## 6. 风险与取舍

- **`last_usage` 实例属性是共享可变状态**：当前所有 LLM 调用串行（`_call_llm` 无并发），安全；若未来并行调用需在那时改为返回值传递，本设计在 openspec 中显式记录该约束。
- **usage 字段各 provider 不一致**：归一化函数对缺失字段一律补 0；baidu/glm 等只要走 OpenAI 兼容客户端返回标准 usage 即有基础数据。
- **by_operation 键含 `(i/N)` 后缀**：聚合按完整操作名分组，同一阶段不同 chunk 各占一行属预期；阶段级看板看 `by_stage`。
