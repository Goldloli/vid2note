## ADDED Requirements

### Requirement: 液态玻璃设计系统(分层玻璃)
系统 SHALL 提供分层液态玻璃视觉:浮起层(侧栏 / 顶栏 / 弹层 / 浮卡)使用 `backdrop-filter: blur()+saturate()` 半透明玻璃,背后背景透出;主内容区卡片使用半透明纯色(非玻璃)以保证可读性。

#### Scenario: 浮起层呈现玻璃
- **WHEN** 用户查看主界面
- **THEN** 侧栏与顶栏呈现 `backdrop-filter` 模糊+饱和的半透明玻璃,mesh 背景透出,带 1px 高光内边

#### Scenario: 内容区保证可读
- **WHEN** 用户查看笔记 / 列表等内容区
- **THEN** 内容卡片为半透明纯色(非 `backdrop-filter` 玻璃),文字对比度满足可读性

#### Scenario: 双主题平滑切换
- **WHEN** 用户切换明 / 暗主题
- **THEN** 玻璃与内容区颜色平滑过渡(过渡 ≤250ms),文字保持可读对比度,选择持久化

### Requirement: 物理动效系统(emil 哲学·克制)
系统 SHALL 提供克制的 iOS spring 动效:可点元素 press `scale(.97)`;弹层从触发点 origin 缩放进入(modal 例外居中);页面切换淡入 + 上移 8px;列表 stagger(40ms);退出比进入快;统一 spring 曲线 `cubic-bezier(0.32,0.72,0,1)`。

#### Scenario: 按压即时反馈
- **WHEN** 用户按下按钮 / 可点元素
- **THEN** 元素 `scale(.97)` 即时回应,松开后 spring 回弹

#### Scenario: 弹层 origin-aware
- **WHEN** 用户从某触发点打开弹层 / 浮卡
- **THEN** 弹层从触发点位置(origin)缩放进入,而非居中(modal 类例外居中)

#### Scenario: reduced-motion 降级
- **WHEN** 用户系统开启「减少动效」
- **THEN** 移除位移 / 缩放类动效,仅保留淡入,保证不引发不适

### Requirement: 流水线节点招牌动效
任务详情的六步流水线节点 SHALL 用动效直观传达状态:节点完成时 spring 弹动 + 成功色光晕;运行中 Apple 蓝呼吸光;失败时抖动 + 警示色;完成段连接线 clip-path 擦除式流光填充。

#### Scenario: 节点完成
- **WHEN** 某节点状态变为 completed
- **THEN** 节点 spring 缩放(1→1.15→1)+ 成功色光晕脉冲一次

#### Scenario: 节点运行中
- **WHEN** 某节点 running
- **THEN** 节点 Apple 蓝呼吸光脉冲(循环)

#### Scenario: 节点失败
- **WHEN** 某节点 failed
- **THEN** 节点横向抖动 + 红色警示色

#### Scenario: 连接线流光
- **WHEN** 上游节点完成
- **THEN** 该段连接线以 clip-path 擦除式流光填充至下游节点

### Requirement: 动态背景与背景可配
系统 SHALL 默认提供动态 mesh 渐变背景(多色径向色斑缓慢漂移),用户可在设置页切换为静态壁纸或纯色;背景动效 SHALL 尊重 `prefers-reduced-motion`(降级为静态首帧)。

#### Scenario: 默认动态 mesh
- **WHEN** 用户首次打开(默认配置)
- **THEN** 背景为多色径向色斑缓慢漂移(20–30s 周期)的 mesh 渐变

#### Scenario: 用户切换背景
- **WHEN** 用户在设置页选择静态壁纸 / 纯色
- **THEN** 背景立即切换并持久化,刷新 / 重启后保留

#### Scenario: 背景降级
- **WHEN** 系统开启减少动效
- **THEN** mesh 停止漂移,呈现静态首帧

### Requirement: 笔记舒适阅读排版
笔记页 SHALL 采用舒适阅读排版:正文限宽 720px 居中;标题用衬线字体;正文行距 1.8;正文字号 16px;代码块 / 引用用玻璃浮卡承载。

#### Scenario: 阅读布局
- **WHEN** 用户打开笔记页
- **THEN** 正文限宽 720px 居中,标题衬线,行距 1.8,字号 16px,长笔记阅读不累

### Requirement: 设计系统沉淀(DESIGN.md)
项目 SHALL 沉淀 `DESIGN.md` 全套设计文档(设计 token 表 + 玻璃组件库 API + 动效规范 + 页面模板 + do/don't + 暗主题对照),供后续页面开发复用,避免风格漂移。

#### Scenario: DESIGN.md 完整产出
- **WHEN** 本次重构完成
- **THEN** 项目根(或 docs/)存在 `DESIGN.md`,含六节(token / 组件库 / 动效规范 / 页面模板 / do-don't / 暗主题),后续新页面可据此复用
