## Context

笔记 / 导图页 per-task，无固定全局路由。侧栏点击需要一个目标任务 id。

## Goals / Non-Goals

**Goals:** 侧栏 +「笔记」「思维导图」页签；点击跳最近完成任务的笔记 / 导图；无任务时友好提示。

**Non-Goals:** 列表页；页签激活态高亮；i18n。

## Decisions

### D1 点击 = 最近一篇（非列表页）

- **Why**：最轻、最快回到上次成果；`useTaskStore` 已有 `completed` getter（最近 10 条完成任务的 slice[0]）。
- **Alt**：列表页（多一次跳转，v1 暂不需要）。

### D2 页签用 `<a class="nav-item" @click.prevent>` 而非 `<router-link>`

- **Why**：目标是动态 id（`/note/:id`），无固定 `to`；用 `<a>` 复用 `.nav-item` 样式（`router-link` 也渲染为 `a`），`@click.prevent` 阻止默认跳转、走 `goLatest`。
- `goLatest(kind)`：先 `tasks.fetchRecent()` 拿最新数据 → `completed[0]` → `router.push('/'+kind+'/'+id)`；无则 `alert` 提示。

## Risks / Trade-offs

- **[无 completed 时点页签无反应]** → `alert` 明确提示去主控台创建。
- **[页签不高亮]** → 跳到 `/note/:id` 后侧栏该页签不高亮（接受，Non-goal）。

## Migration Plan

前端增量，无数据迁移。回滚：移除 App.vue 两页签 + goLatest。
