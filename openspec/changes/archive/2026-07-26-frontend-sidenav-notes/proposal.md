## Why

笔记页 / 思维导图页是 per-task 的（`/note/:id`、`/mindmap/:id`），之前只能从主控台 / 历史 / 任务详情进入，**侧栏没有直接入口**，用户无法一键回到最近一篇笔记或导图。`web-frontend` spec 的导航 Requirement 要求侧栏含笔记 / 思维导图入口。本 change 在侧栏补这两个页签，点击跳转「最近一篇」（最近完成任务的笔记 / 导图）。

## What Changes

- 侧栏新增「笔记」「思维导图」页签（位于主控台与历史之间）。
- 点击 → 取 `tasks.completed[0]`（最近完成任务的 id）→ 跳 `/note/:id` 或 `/mindmap/:id`。
- 无已完成任务时弹窗提示「请先在主控台创建任务」。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `web-frontend`：修订「应用骨架与六页导航」——侧栏全局入口明确含「笔记」「思维导图」，点击定位到最近一篇；任务详情仍由主控台 / 历史进入（per-task，不在全局侧栏）。

## Impact

- **前端**：`App.vue`（侧栏 +2 页签 + `goLatest` 方法，引入 `useRouter`）。
- **spec**：`web-frontend` MODIFIED 导航 Requirement。
- **测试**：`npm run build`；手动点侧栏页签验证跳转。

## Non-goals

- 笔记 / 导图**列表页**（本 change 用「最近一篇」最轻方案；列表页留后续）。
- 全 UI 中英文 i18n（单独 change `frontend-i18n`）。
- 页签的 per-task 激活态高亮（点击跳到 `/note/:id` 后，侧栏页签不高亮，可后续按 path 前缀匹配）。
