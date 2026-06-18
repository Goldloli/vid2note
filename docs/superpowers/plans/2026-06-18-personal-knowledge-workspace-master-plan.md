# Personal Knowledge Workspace Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有视频转笔记桌面应用渐进升级为本地优先、Obsidian 兼容、由 Agent 通过 ChangeSet 维护且能回到视频证据的个人知识工作台。

**Architecture:** 保留 Electron + Vue 3/Vite、FastAPI 与 `vid2note_core` 的三层边界；Markdown Vault 是唯一知识事实源，SQLite 只保存任务、会话与可重建状态。实施拆为六个可独立验收阶段，严格按 Phase 0 → 5 顺序推进，不引入向量数据库、Node 常驻控制面或外部 Agent 直写正式 Vault。

**Tech Stack:** Python 3.11、FastAPI、Pydantic、SQLite、pytest、Vue 3、TypeScript、Pinia、Vue Router、CodeMirror 6、Electron、Playwright、FFmpeg、yt-dlp。

---

## 1. 冻结输入

- 目标规格：`docs/superpowers/specs/2026-06-18-personal-knowledge-workspace-design.md`
- 前端视觉参考：`前端模板设计/knowledge-workspace-v1`
- Agent Runtime 参考：`/Users/gejiawei/Desktop/ai_code/项目参考/open-design-main`
- 媒体任务参考：`/Users/gejiawei/Desktop/ai_code/项目参考/BiliTools-master`
- ASR 边界参考：`/Users/gejiawei/Desktop/ai_code/项目参考/AsrTools-main`
- 下载上游参考：`/Users/gejiawei/Desktop/ai_code/项目参考/yt-dlp-master`

若实现需要改变以下决策，先修订规格，不在执行中静默改架构：

- 不使用向量数据库；
- Vault 是知识正文事实源；
- Agent/Compiler 只能通过 ChangeSet 写 Wiki；
- 用户直接编辑必须记录 human-edit 日志；
- 默认自治模式为 A（审批）；
- 外部 CLI 只在临时工作区运行；
- 保留 Electron + Vue + FastAPI + Python Core。

## 2. 计划套件与依赖顺序

| 顺序 | 计划 | 可验证交付物 | 进入条件 | 退出条件 |
|---|---|---|---|---|
| 0 | `2026-06-18-knowledge-phase0-trusted-baseline.md` | 可信任务运行基线 | 当前 `main` | 固定本地视频由真实 Worker 稳定生成带时间证据的来源笔记 |
| 1 | `2026-06-18-knowledge-phase1-control-plane-shell.md` | 类型化控制面与统一外壳 | Phase 0 全绿 | 旧视频链路在统一外壳运行，OpenAPI/TS 契约可校验 |
| 2 | `2026-06-18-knowledge-phase2-vault-media-evidence.md` | Vault 与媒体证据 | Phase 1 全绿 | 来源笔记能跳转正确视频区间，删除状态库不丢知识正文 |
| 3 | `2026-06-18-knowledge-phase3-wiki-compiler.md` | Wiki Compiler 与 ChangeSet | Phase 2 全绿 | 第二来源能增强既有页面并处理重复、矛盾和冲突 |
| 4 | `2026-06-18-knowledge-phase4-agent-runtime.md` | Built-in/Codex/Claude Runtime | Phase 3 全绿 | 三种 Runtime 基于同一 Wiki 回答并通过 ChangeSet 建议写回 |
| 5 | `2026-06-18-knowledge-phase5-workspace-ui.md` | 完整知识工作台 | Phase 4 全绿 | 桌面 UI 完成导入、审批、阅读、问答、证据回看与 Wiki 维护 |

不得并行开发 Phase 2–4 的正式写入路径。Phase 1 的 UI shell 可以在 Phase 0 后与 contracts 工作并行，但合并前必须使用同一 OpenAPI schema。

## 3. 跨阶段文件边界

```text
core/src/vid2note_core/
├── paths.py                 # Phase 0：唯一运行路径解析
├── source/                  # Phase 2：来源身份、逐字稿和来源笔记注册
├── vault/                   # Phase 2：磁盘协议、页面访问、日志、监听
├── media/                   # Phase 2：时间证据、frame/clip 生成与缓存
├── wiki/                    # Phase 3：索引、ChangeSet、校验、应用、lint
└── agents/                  # Phase 4：统一事件、Runtime、临时工作区与 adapters

server/src/vid2note_server/
├── dependencies.py          # Phase 0/1：显式依赖与 app state
├── schemas/                 # Phase 1 起：Pydantic API 事实源
└── api/                     # 薄路由；不放领域逻辑

desktop/src/renderer/
├── api/generated/           # Phase 1：OpenAPI 生成类型
├── components/workspace/    # Phase 1/5：共享四区外壳
├── stores/                  # Phase 1–5：单一状态源
└── views/                   # Phase 1/5：独立专注视图
```

规则：领域模型在 Core，HTTP schema 在 Server，展示模型在 Renderer。禁止 API handler 直接拼 Wiki 文件，禁止 Vue 组件解析任意 CLI 输出。

## 4. 每阶段统一执行门禁

- [ ] 从独立 worktree 开始，确认 `git status --short` 只包含该阶段文件。
- [ ] 先运行该阶段列出的 baseline 命令并保存结果。
- [ ] 每个行为先写失败测试，再写最小实现。
- [ ] 每个 Task 完成后只提交 Task 列出的文件。
- [ ] Python 变更运行 `uv run pytest`、Ruff、mypy；Renderer 变更运行类型检查、构建与相关 Playwright。
- [ ] 更新 CodeGraph：`codegraph update`，再用 `codegraph status` 确认索引最新。
- [ ] 对照目标规格 §7–18 做阶段覆盖检查。
- [ ] 不提交 `.DS_Store`、安装包、缓存、模型或生成媒体。

## 5. 规格覆盖矩阵

| 目标规格 | 实施计划 |
|---|---|
| §5 当前基线与实施门槛 | Phase 0 Tasks 1–7 |
| §6 系统架构、进程边界 | Phase 0 Task 2、Phase 1 Tasks 1–3 |
| §7 Vault 磁盘协议 | Phase 2 Tasks 1–5、7 |
| §8 Index-first 索引 | Phase 3 Task 2 |
| §9 Source Pipeline | Phase 0 Task 7、Phase 2 Tasks 3–4 |
| §10 Wiki Compiler/ChangeSet/自治 | Phase 3 Tasks 1、3–7 |
| §11 Agent Runtime | Phase 4 Tasks 1–8 |
| §12 Media Citation | Phase 2 Task 6、Phase 5 Task 4 |
| §13 主界面与可访问性 | Phase 1 Tasks 4–6、Phase 5 Tasks 2–8 |
| §14 API 与共享 Contracts | Phase 1 Tasks 1–3；Phase 2–4 各 API task |
| §15 一致性与恢复 | Phase 0 Tasks 3–6、Phase 2 Task 7、Phase 3 Task 5 |
| §16 安全与隐私 | Phase 0 Tasks 1、5–7；Phase 2 Task 2；Phase 4 Tasks 3–7 |
| §17 测试与评估 | Phase 0 Task 7、Phase 3 Task 7、Phase 4 Task 8、Phase 5 Task 8 |
| §18 分阶段路线 | 本计划套件 Phase 0–5 |

## 6. MVP 终局验收

执行 Phase 5 最终 E2E，固定顺序如下：

```text
导入 source A
→ Worker 生成 transcript/source note
→ Compiler 提出 ChangeSet A
→ 用户批准并写入 wiki page/index/log
→ 导入同主题 source B
→ Compiler 对同一 page 提出增强或矛盾
→ 用户批准
→ Agent 读取 index/page 回答
→ 点击证据卡播放正确时间段
→ 重启 Electron
→ 页面、引用、ChangeSet 历史仍存在
```

最终必须同时满足：

- `uv run pytest` 无失败；
- `uv run ruff check .` 与 `uv run ruff format --check .` 通过；
- `uv run mypy core/src server/src` 通过；
- Renderer 类型检查与 production build 通过；
- Playwright MVP E2E 通过；
- 仓库不存在向量数据库依赖；
- 外部 Agent 测试证明正式 Vault 未被直接写入；
- 删除 `.vid2note/state.sqlite3` 后 Wiki Markdown 仍完整可读。

## 7. 版本与提交策略

每个 Task 使用小提交，提交前缀固定：

```text
fix(runtime): centralize data root paths
feat(contracts): generate renderer types from OpenAPI
feat(workspace): add the unified desktop shell
feat(vault): register pipeline outputs as sources
feat(media): generate evidence clips on demand
feat(wiki): apply and revert changes atomically
feat(agent): expose normalized agent sessions
test(e2e): verify the complete knowledge workspace
docs: record third-party distribution obligations
```

每个阶段只在其退出条件真实通过后进入下一阶段；测试被 skip、xfail 或 mock 掉真实 Worker 时不算退出。
