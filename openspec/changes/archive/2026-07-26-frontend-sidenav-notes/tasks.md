## 1. 侧栏页签

- [x] 1.1 `App.vue` 侧栏在主控台与历史之间加「笔记」「思维导图」页签（`<a class="nav-item" @click.prevent="goLatest(kind)">`）
- [x] 1.2 引入 `useRouter`，实现 `goLatest(kind)`：`tasks.fetchRecent()` → `completed[0]` → `router.push('/'+kind+'/'+id)`；无则 `alert` 提示

## 2. 测试与验收

- [x] 2.1 `cd frontend && npm run build` 通过
- [ ] 2.2 docker 重建 + 手动点侧栏「笔记」「思维导图」验证跳转最近一篇 / 无任务提示（**需容器验证**）
- [x] 2.3 `bd` 建任务跟踪
