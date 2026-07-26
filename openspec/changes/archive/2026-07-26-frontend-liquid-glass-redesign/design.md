# frontend-liquid-glass-redesign · 技术设计

> 风格定位:Apple Liquid Glass(macOS Tahoe 26 + Apple Music 混合)—— 浮起层玻璃、内容区干净、克制专业动效。
> 哲学依据:emil-design-eng(细节复合、spring 物理、origin-aware、press 反馈、动效有目的不滥用)。

## Context

v1 前端 = 扁平硬色 CSS(hex)+ 无玻璃 + 无动效 + oklch 颜色(兼容性隐患)。功能可用但「初级」。
本次重构不碰后端,纯前端换一套**液态玻璃设计系统**,并把现有 6 页全部迁移,沉淀 `DESIGN.md`。

约束:Vue3 + 纯 CSS(不换框架);本地 Docker Web 应用(localhost:8761);双主题;性能友好(背景动效尊重 reduced-motion)。

## Goals / Non-Goals

**Goals**
1. 一套玻璃设计系统(token + 组件 + 动效 + 页面模板),任何浏览器稳定渲染
2. 现有 6 页迁移到玻璃组件,主控台/任务详情/笔记三页极致打磨
3. 招牌视觉:任务详情流水线节点(完成 spring+光晕 / 运行呼吸 / 失败抖动 / 连接线流光)
4. 笔记页舒适阅读(衬线标题 + 1.8 行距 + 限宽)
5. 沉淀 `DESIGN.md`(后续页面开发的设计宪法)
6. 双主题(默认亮)+ 背景(动态 mesh 默认,可切)

**Non-Goals**
- 后端 / API / 数据模型(不动)
- 新功能页(笔记库/导图库/ASR 设置页 —— 留 feature change)
- 换框架 / 引 Web 字体

## Decisions

### D1. 风格定位:Tahoe + Apple Music 混合(分层玻璃)
**决策。** 浮起层(侧栏 / 顶栏 / 弹层 / 浮卡)= 玻璃(`backdrop-filter`);主内容区卡片 = 半透明纯色(可读性 + 性能)。
**理由。** 全玻璃(`backdrop-filter` 叠 ≥4 层)会乱 + 卡;内容区不玻璃保证可读性;浮起感才需要玻璃。emil 哲学:浮起的才是玻璃。
**Alternatives。** 全玻璃(视觉冲击但乱+卡,否决);纯平面(无高级感,否决)。

### D2. 双主题(默认亮)+ Apple 蓝 `#0A84FF`
**决策。** `[data-theme="light|dark"]` CSS 变量切换,默认亮;强调色 `#0A84FF`(亮)/ `#0A84FF`(暗微调);localStorage 持久化。
**理由。** 液态玻璃在亮色下高光折射最漂亮;Apple 蓝和液态玻璃最搭,免费拿到系统一致感。
**Alternatives。** 暗为主(深邃但玻璃高光弱);品牌自定义色(无必要,Apple 蓝够)。

### D3. 背景:动态 mesh 渐变漂移(默认)+ 设置可切静态/纯色
**决策。** body 铺 3–4 个径向色斑(Apple 蓝紫粉系),`@keyframes` 缓慢漂移(20–30s);设置页三选一(动态 mesh / 静态壁纸 / 纯色噪点);`prefers-reduced-motion` 降级为静态首帧。
**理由。** 玻璃必须背后有内容透 —— 纯色背景上玻璃等于没有。mesh 最有「液态」感。用户可切静态(性能/偏好)。
**Alternatives。** 纯静态壁纸(稳但无液态感);纯色(玻璃失效,否决)。

### D4. 动效:emil 哲学(克制专业)+ iOS spring
**决策。** 统一 iOS spring `cubic-bezier(0.32,0.72,0,1)`;press `scale(.97)`(按钮/可点元素);弹层 origin-aware(transform-origin 对齐触发点,modal 例外居中);页面切换淡入+`translateY(8px→0)`;列表 stagger 40ms;退出比进入快(进 250ms / 出 150ms);`prefers-reduced-motion` 移除位移只留淡入。
**理由。** emil:动效必须有目的,频繁操作别动(键盘快捷键零动效);press 即时回应;origin-aware 让弹层「从触发点起身」;退出干脆。
**Alternatives。** 丰富活泼(抢戏,违克制);无动效(初级感,否决)。

### D5. 招牌:流水线节点动效(任务详情)
**决策。** 六节点 DAG:完成 `spring scale(1→1.15→1)` + 成功色光晕脉冲;运行中 Apple 蓝呼吸光(`@keyframes` opacity/box-shadow);失败 `shake`(translateX 抖动)+ 红色;连接线 `clip-path` 擦除式流光填充(完成段)。
**理由。** 流水线是 vid2note 招牌视觉,进度状态用动效直观传达;spring 物理感高级。
**Alternatives。** 静态状态色(无反馈,初级);全动画(性能,否决)。

### D6. 组件库:玻璃描边次级按钮 + Apple 蓝实心主按钮
**决策。** `.btn-app`(玻璃描边:半透明 + 1px 高光边 + press scale);`.btn-app-primary`(Apple 蓝实心 + 白字 + press scale + hover 加深);`.btn-app-ghost`(透明文字)。卡片 `.glass-card` hover `translateY(-2px)` + 阴影加深(克制);选中 Apple 蓝描边光晕。
**理由。** 主次层级清晰(主按钮蓝实心最重,次级玻璃描边);hover 抬升给「可点」暗示但克制。
**Alternatives。** 全玻璃按钮(主次不分);全实心(沉重)。

### D7. 字体:系统 SF Pro 栈
**决策。** `--font: -apple-system, "SF Pro Display", "SF Pro Text", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif`;笔记标题混用衬线(`"New York", "Songti SC", serif`)做阅读感。
**理由。** 免费、和 macOS/iOS 完全一致、零 Web 字体加载;苹果味最正。
**Alternatives。** 引入 Inter + 思源(Web 字体加载 + 维护,否决)。

### D8. 笔记页:舒适阅读排版
**决策。** 限宽 720px 居中;标题衬线 + 正文 1.8 行距;`font-size: 16px`;代码块/引用玻璃浮卡;章节大纲侧栏定位。
**理由。** 像 Apple Books 的阅读体验,长笔记不累。
**Alternatives。** 技术文档风(紧凑,阅读累);卡片化每章(打断流,否决)。

### D9. 性能:只动 transform/opacity + backdrop-filter 限层
**决策。** 所有动效只动 `transform`/`opacity`(GPU);`backdrop-filter` 并发 ≤3 层(侧栏+顶栏+一个浮卡);mesh 背景用 `will-change: transform` + reduced-motion 降级。
**理由。** emil:动 width/height/padding 触发 layout;backdrop-filter 多层卡(尤其 Safari)。
**Alternatives。** 无限制(卡顿,否决)。

### D10. 交付:DESIGN.md 全套
**决策。** 产出 `DESIGN.md`(项目根):① 设计 token 表(颜色/玻璃/圆角/阴影/动效曲线/字号)② 玻璃组件库 API(类名/props/变体/示例)③ 动效规范(场景→曲线→时长表)④ 页面模板(主控台/详情/列表/阅读/设置 骨架)⑤ do/don't ⑥ 暗主题对照表。开发完成后沉淀,后续页面据此复用。
**理由。** 用户明确要求;避免后续页面风格漂移。

## Risks / Trade-offs

- **[风险] `backdrop-filter` 多层卡顿(Safari 尤甚)** → [缓解] D9 限 ≤3 层并发;主内容区不玻璃;reduced-motion 降级。
- **[风险] mesh 背景 GPU 占用** → [缓解] 缓慢漂移(20–30s)+ `will-change` + reduced-motion 静态首帧 + 用户可切静态。
- **[风险] 玻璃上文字对比度不足** → [缓解] 内容区不玻璃(半透明纯色)+ 玻璃层用 `rgba` 深色文字 + 暗主题调高对比。
- **[Trade-off] 系统 SF Pro 栈 = 非 Mac 用户 fallback** → 可接受(多数目标用户 Mac;fallback 仍是系统无衬线)。

## DESIGN.md 大纲(开发后沉淀)

1. **设计 token**:颜色(亮/暗)、玻璃(blur/saturate/alpha/border-highlight)、圆角、阴影、动效曲线(spring-ios/spring-drawer/ease-out)、字号层级
2. **玻璃组件库**:每个组件的类名 / HTML 结构 / 变体 / 用法示例(glass-sidebar/glass-bar/glass-card/btn-app/input-app/badge-app/pipeline-node ...)
3. **动效规范**:场景 → 是否动 → 曲线 → 时长 表(press/弹层/页面切换/stagger/流水线节点)
4. **页面模板**:主控台 / 任务详情 / 列表(历史) / 阅读(笔记) / 表单(设置) 的骨架与布局规则
5. **do / don't**:动效别滥用(频率)、玻璃别全屏、退出比进入快、origin-aware、reduced-motion 兜底
6. **暗主题对照**:每个 token 的亮/暗值

## Open Questions
1. 静态壁纸:用程序生成的渐变图,还是内置一张抽象 PNG?(倾向程序生成,零资源)
2. 拖拽场景:任务卡拖拽排序 是否本次做?(v1 无排序,可留后续)
3. `@vueuse/motion` 是否引入?(纯 CSS 能做 90%;拖拽惯性再引)
