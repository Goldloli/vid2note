# frontend-liquid-glass-redesign 实现任务清单

> 按「设计系统地基 → 玻璃组件库 → 动效系统 → 6 页迁移 → DESIGN.md 沉淀」推进。纯前端,不碰后端。

## 1. 设计系统地基

- [x] 1.1 重写 `frontend/src/styles/app.css`:设计 token(颜色亮/暗、玻璃 blur/saturate/alpha/高光边、圆角、阴影、动效曲线 spring-ios/spring-drawer/ease-out、字号层级)+ reset + `[data-theme]` 变量 + SF Pro 字体栈(验证:浏览器打开,亮/暗主题切换平滑,token 变量生效)
- [x] 1.2 动态 mesh 背景:body 铺 3–4 个 Apple 蓝紫粉径向色斑,`@keyframes` 缓慢漂移(20–30s)+ `will-change: transform`;`prefers-reduced-motion` 静态首帧(验证:背景缓慢漂移;reduced-motion 下静止)
- [x] 1.3 暗主题玻璃调色:`rgba(30,30,40,.55)` 系列玻璃 + 对比度可读(验证:暗主题下玻璃深邃、文字清晰)

## 2. 玻璃组件库(CSS + 组件)

- [x] 2.1 `glass-sidebar` / `glass-bar`(顶栏吸顶)/ `glass-card`(浮卡):backdrop-filter + 半透明 + 1px 高光内边 + 双层柔光阴影(验证:浮在 mesh 上玻璃感明显,边缘高光)
- [x] 2.2 `glass-popover`(弹层):origin-aware + spring 进入 + 退出比进入快(验证:从触发点缩放进入)
- [x] 2.3 按钮:`btn-app`(玻璃描边次级)+ `btn-app-primary`(Apple 蓝实心)+ `btn-app-ghost`;全部 press `scale(.97)`(验证:按下即时回弹)
- [x] 2.4 `input-app`(玻璃框 + focus 光晕)/ `badge-app` / `chip-app` / `progress-app`(流光)(验证:focus 蓝光晕;chip 选中蓝)
- [x] 2.5 招牌 `pipeline-node` 组件:完成 spring+光晕 / 运行呼吸 / 失败抖动 / 连接线 clip-path 流光(验证:四态动效正确,见 spec 场景)

## 3. 动效系统

- [x] 3.1 页面切换:router-view 淡入 + `translateY(8px→0)`,250ms spring-ios(验证:切页有上移淡入)
- [x] 3.2 列表 stagger:卡片/行进场 40ms 错落(验证:列表错落进场)
- [x] 3.3 卡片 hover 抬升 `translateY(-2px)` + 阴影加深(克制);选中 Apple 蓝描边光晕(验证:hover 轻抬;选中蓝光)
- [x] 3.4 `prefers-reduced-motion` 全局兜底:移除位移/缩放,仅淡入(验证:系统减少动效下静止)

## 4. 页面迁移(6 页换玻璃,三页极致)

- [x] 4.1 `App.vue`:玻璃侧栏 + 玻璃顶栏 + mesh 背景 + 主题切换(验证:侧栏/顶栏玻璃浮于 mesh)
- [x] 4.2 主控台(极致):输入区 + ASR/截图选择 + 进行中任务卡(流水线节点招牌动效)+ 最近完成;空状态引导
- [x] 4.3 任务详情(极致):六节点流水线(招牌动效)+ 玻璃日志终端 + 产物 Tab + 重跑/取消(确认弹层 origin-aware)
- [x] 4.4 笔记(极致):舒适阅读排版(限宽 720 + 衬线标题 + 1.8 行距)+ 大纲侧栏定位 + 复制/导出
- [x] 4.5 思维导图 / 历史 / 设置:换玻璃组件 + 卡片化
- [x] 4.6 设置页加「背景」选择(动态 mesh / 静态壁纸 / 纯色),持久化

## 5. 沉淀

- [x] 5.1 产出 `DESIGN.md`(项目根):① 设计 token 表 ② 玻璃组件库 API(类名/结构/变体/示例)③ 动效规范(场景→曲线→时长表)④ 页面模板(主控台/详情/列表/阅读/设置)⑤ do/don't ⑥ 暗主题对照(验证:含六节,后续页面可据此复用)

## 6. 验证

- [x] 6.1 `npm run build` 通过;docker compose up 后 8761 可访问
- [x] 6.2 playwright 验证:6 页渲染 + 三页(主控台/任务详情/笔记)视觉/动效到位 + 流水线节点四态动效 + 双主题切换 + 背景切换 + reduced-motion 降级
