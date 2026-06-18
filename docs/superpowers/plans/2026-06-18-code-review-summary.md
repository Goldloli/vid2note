# vid2note 全面 Code Review 报告与优化路线图

> 生成日期：2026-06-18
> 审查范围：core（后端流水线/worker/ASR/LLM/存储）、server（FastAPI）、desktop（Electron+Vue3）、测试、配置、部署、CI、文档
> 审查方法：4 个并行 explore agent 逐文件扫描 + 实跑测试套件 + ruff/mypy 验证

---

## 一、Review 发现总览

四个子系统共发现 **约 60 个问题**，按严重度分布：

| 严重度 | 数量 | 含义 |
|--------|------|------|
| Critical | 8 | 功能性阻断 / 安全漏洞 / 测试全红 |
| High | 33 | 影响可靠性、可用性、正确性 |
| Medium | 30 | 代码质量、可维护性、一致性 |
| Low | 14 | 小瑕疵、死代码 |

### 七大主题问题

1. **失败时假装成功（核心信任问题）** — mock ASR 兜底、`_simple_format` LLM 兜底、`MockLLM` 默认，系统标记 COMPLETED 却产出垃圾内容
2. **错误类型擦除** — 所有 LLM 适配器把异常包成 `RuntimeError`，精心定义的 `LLMRateLimited`(retryable=True) 等类型从未被抛出；`retryable` 元数据全是死代码
3. **无重试/无超时/无优雅关闭** — worker 无信号处理、subprocess 无 timeout、LLM 无退避重试，瞬时错误永久失败
4. **前后端契约断裂（6 处）** — rerun 空操作、artifacts 字段路径错位、export_mindmap 永不发送、配置字段被丢弃、思维导图渲染死代码
5. **无法下载产物** — 后端零个 `FileResponse` 端点，用户拿不到生成的 .md/.srt 文件
6. **死代码堆积** — `asrtools.py`、`nodes.py` stub、`youget.py`、`utils/security.py`、PyInstaller 脚本（已被 venv 方案取代）
7. **配置旁路** — worker 直接读环境变量，无视 `ConfigManager`/keychain，UI 里保存的 key 对执行不可见

### 测试与 CI 现状（实跑结果）

```
pytest -x:  FAILED（test_asr_factory 断言过时）
pytest:     1 failed, 165 passed
ruff check: 96 errors（93 在 vendored bk_asr/）
mypy:       31 errors（全在 vendored bk_asr/）
```

**CI 的 lint 和 test-python 两个 job 当前都是 RED。**

---

## 二、优化路线图（4 个阶段）

我按依赖关系把 60 个问题拆成 4 个独立可交付的阶段。每阶段是一个独立的计划文档，可单独执行和验证。

| 阶段 | 目标 | Task 数 | 覆盖问题 | 预计 |
|------|------|---------|----------|------|
| **Phase 1** | CI/测试恢复绿灯 | 6 | 测试失败、ruff/mypy、缺测试 | ~2h |
| **Phase 2** | 前后端契约对齐 | 6 | 6 个 Critical 契约 bug | ~3h |
| **Phase 3** | 产物下载/导出 API | 5 | 无 FileResponse 端点 | ~2h |
| **Phase 4** | 稳定性与错误处理 | 7 | 假成功、无重试、CORS、健康检查 | ~4h |

### 执行顺序与依赖

```
Phase 1（解锁 CI）── 必须最先，否则后续改动无法验证
     ↓
Phase 2（契约对齐）── 让 UI 可用
     ↓
Phase 3（导出 API）── 补功能缺口
     ↓
Phase 4（稳定性）── 提升可靠性，依赖前 3 阶段的测试基础
```

Phase 2 和 Phase 3 之间无强依赖，可并行。Phase 4 依赖 Phase 1 的测试基础（要为新错误处理逻辑写测试）。

### 计划文档

- [`2026-06-18-phase1-ci-tests-green.md`](./2026-06-18-phase1-ci-tests-green.md) — CI/测试恢复绿灯
- [`2026-06-18-phase2-contract-alignment.md`](./2026-06-18-phase2-contract-alignment.md) — 前后端契约对齐
- [`2026-06-18-phase3-artifact-export-api.md`](./2026-06-18-phase3-artifact-export-api.md) — 产物下载/导出 API
- [`2026-06-18-phase4-stability-error-handling.md`](./2026-06-18-phase4-stability-error-handling.md) — 稳定性与错误处理

---

## 三、未纳入本轮计划的问题（后续迭代）

以下为 Medium/Low，可独立处理，不阻塞主功能：

- **core**: EventBus.publish 非线程安全、sync ASR 阻塞事件循环、DB 无迁移版本控制、`INSERT OR REPLACE` 抹除时间戳、artifact `{node}_{name}` 命名脆弱、DAG resume artifact 键错误
- **server**: SSE 无断连检测/无历史回放、无分页、无鉴权/限流、logs.py 是空 stub、两个重复的任务创建端点（/tasks vs /process/start）
- **desktop**: 无全局错误处理、无后端离线 UI、无单实例锁、Note.vue 手写 markdown 渲染器、useReveal 可能永久不可见、硬编码 provider chip、Element Plus 死依赖
- **工程**: 删除死脚本（PyInstaller build.py/spec）、修 docs/api.md 错误端点、.env.example 补 `_MODEL` 变量、dist-electron-v* 清理、轮换已暴露的 DASHSCOPE_API_KEY

---

## 四、执行方式建议

每个阶段计划都遵循 TDD（先写失败测试→实现→验证）+ 频繁 commit。推荐用 **subagent-driven-development**：每个 Task 派一个全新 subagent 执行，主会话负责 review，快速迭代。

想开始的话，告诉我从哪个阶段起步——**建议从 Phase 1 开始**，因为它解锁 CI，是所有后续工作的前提。
