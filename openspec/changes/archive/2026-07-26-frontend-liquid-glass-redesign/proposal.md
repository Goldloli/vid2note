## Why

v1 前端功能可用但视觉「初级」:扁平硬色 CSS、无玻璃材质、无动效、oklch 颜色有兼容性隐患,与「高级本地工具」定位不符。本次把前端重构为 **Apple Liquid Glass(液态玻璃)**风格(macOS Tahoe + Apple Music 混合气质),提升审美与交互品质,并沉淀一套设计系统(`DESIGN.md`)供后续所有页面复用。

## What Changes

**设计系统重写**(替换现有扁平 CSS):
- 玻璃材质 token:`backdrop-filter: blur()+saturate()` + 半透明 + 1px 高光内边 + 双层柔光阴影
- 动态 mesh 渐变背景(多色径向色斑缓慢漂移),**设置页可切静态壁纸 / 纯色**
- iOS spring 动效曲线 `cubic-bezier(0.32,0.72,0,1)`
- 双主题(默认亮)+ 强调色 Apple 蓝 `#0A84FF`
- 字体改系统 SF Pro 栈(`-apple-system, "SF Pro Display", "PingFang SC", ...`)

**玻璃组件库**(全部带 press 反馈 / origin-aware / hover):
- `glass-sidebar` / `glass-bar`(顶栏)/ `glass-card`(浮卡)/ `glass-popover`(弹层)
- `btn-app`(玻璃描边次级)+ `btn-app-primary`(Apple 蓝实心)
- `input-app` / `badge-app` / `chip-app` / `progress-app`
- 招牌:**流水线节点组件**(完成 spring+光晕 / 运行呼吸 / 失败抖动 / 连接线流光)

**动效系统**(emil 哲学,克制专业):
- 按钮 `press: scale(.97)` / 弹层 origin-aware spring / 页面切换淡入+上移 8px / 列表 stagger 40ms / 拖拽物理惯性
- `prefers-reduced-motion` 兜底(降级为静态)

**6 页全换玻璃**,其中 **主控台 / 任务详情 / 笔记** 三页极致打磨:
- 笔记页:舒适阅读排版(衬线标题 + 1.8 行距 + 限宽 720px)

**设置页加「背景」选择**(动态 mesh / 静态壁纸 / 纯色)

**沉淀 `DESIGN.md`**(全套:token 表 + 玻璃组件库 API + 动效规范 + 页面模板 + do/don't + 暗主题对照)

### Non-goals(本次不做)
- 不改后端逻辑 / API(纯前端重构)
- 不加新功能页(笔记库 / 导图库 / ASR 设置页 —— 留后续 feature change)
- 不换框架(Vue3 + 纯 CSS 可达液态玻璃,不引 React)
- 不引 Web 字体(用系统 SF Pro 栈,零加载)

## Capabilities

### Modified Capabilities
- `web-frontend`: 视觉 / 动效 / 背景 / 排版 全面升级到液态玻璃设计系统(spec delta 见 `specs/web-frontend/spec.md`)

### New Capabilities
(无 —— 本次只升级现有 web-frontend 的视觉/交互要求,不新增能力域)

## Impact

- **代码**:纯 `frontend/`(`src/styles/app.css` 重写 + `src/components/` 玻璃组件库新增 + `src/views/` 6 页改造 + `src/App.vue` 布局)
- **依赖**:可选引入 `@vueuse/motion`(Vue 版 Motion,用于拖拽/弹簧),否则纯 CSS + WAAPI
- **不动**:后端、API、Docker、数据模型
- **产物**:`DESIGN.md`(项目根或 `docs/`),作为后续页面开发的设计宪法
