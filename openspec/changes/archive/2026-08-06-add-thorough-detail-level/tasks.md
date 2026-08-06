## 1. 后端：档位定义与校验白名单

- [x] 1.1 `backend/src/prompts/detail_level.py`：`DETAIL_LEVEL_INSTRUCTIONS` 增加 `thorough` 条目与中文指令文本（单一事实源；`normalize_detail_level`/`detail_instruction` 自动放行）
- [x] 1.2 `backend/src/runtime/settings.py`：`_DETAIL_LEVELS` 加入 `thorough`（避免快照脏值静默回落 balanced）
- [x] 1.3 `backend/src/runtime/task_service.py`：`_SUPPORTED_NOTE_DETAIL_LEVELS` 加入 `thorough`（API 创建任务拒绝点）
- [x] 1.4 `backend/src/api/v1/settings.py`：`_ENUM_ALLOWED["note.detail_level"]` 加入 `thorough`（设置写入校验点）
- [x] 1.5 `backend/scripts/verify_settings_sync.py`：`DETAIL_VALUES` 加入 `thorough`（E2E 同步脚本 index 对齐）

## 2. 后端：双钴引擎实现

- [x] 2.1 新增 `SimpleProcessor._generate_thorough_with_fullcontext(subtitle_text, *, pdf_structure, extract_images)`，平级于 `_generate_exhaustive_with_understanding`；复用 `_call_llm`/`_report_usage`/`_sanitize_content`/`_clean_markdown_output`
- [x] 2.2 实现阶段 1 全局理解 prompt：全文 + 规划指令 → 6-8 章大纲 JSON（title/course_overview/terminology/chapters[purpose+key_points]），恰好 1 次调用
- [x] 2.3 实现阶段 2 分章深写：每章消息链 `[SYS, USER1(全文+规划), assistant(大纲), user(本章指令)]`；前缀跨章逐字节稳定（同对象 `json.dumps(ensure_ascii=False, indent=2)`、静态 `detail_instruction("thorough")`、确定性 `_sanitize_content`）
- [x] 2.4 深写指令硬化：保留字幕所有数据/案例/边界、强制使用 terminology 中 confidence=high 的 canonical 专名、规范 Markdown、标题编号统一；`operation_name` 用「比较详细字幕理解」「比较详细章节初稿(i/n)」复用现有中文关键词
- [x] 2.5 实现阶段 3 机械组装：front matter（标题 + course_overview）+ 按大纲顺序拼接章节；无 LLM 重写
- [x] 2.6 `process()` 在 PDF / 无 PDF 两条路径各加 `thorough` 分流（优先于 exhaustive 判断）；全文超过安全阈值（如 50 万字符）时退回 exhaustive 或抛明确错误
- [x] 2.7 `extract_images=True` 时深写指令追加 `SCREENSHOT_INSTRUCTION`（沿用现有三处模式），与 runner `_embed_screenshots` 兼容

## 3. 前端：档位选项与 i18n

- [x] 3.1 `frontend/src/views/Settings.vue`：`detailLevels` 数组在 `detailed` 与 `exhaustive` 之间插入 `{value:'thorough', label:'settings.detail.thorough', hint:'settings.detail.thoroughHint'}`
- [x] 3.2 `frontend/src/views/Console.vue`：创建任务下拉在 detailed 与 exhaustive 之间插入 `<option value="thorough">`
- [x] 3.3 `frontend/src/locales/zh.js`：`detail` 加 `thorough:'比较详细'` 与 `thoroughHint`（说明全文常驻深度引擎、质量近超详细、成本约其 1/7）
- [x] 3.4 `frontend/src/locales/en.js`：`detail` 加 `thorough:'Thorough'` 与 `thoroughHint`

## 4. 测试与校验

- [x] 4.1 更新 `backend/tests/test_note_detail.py`：四档断言（`list(DETAIL_LEVEL_INSTRUCTIONS)`、`len==4`）改为五档
- [x] 4.2 新增双钴引擎单测（RecordingLLM 桩）：消息链结构与跨章前缀稳定、机械组装不变量、空输出/解析失败抛错、超长退回 exhaustive
- [x] 4.3 `openspec validate add-thorough-detail-level --strict` 通过
- [x] 4.4 `cd backend && .venv/bin/python -m pytest` 全绿
- [x] 4.5 `cd frontend && npm run build` 通过
- [x] 4.6 已由后续 `reduce-note-cost-and-asr-latency` 取代：产品决定删除新任务的 `thorough`，历史值映射为 `exhaustive`，因此不再执行已失去产品入口的对比基准
