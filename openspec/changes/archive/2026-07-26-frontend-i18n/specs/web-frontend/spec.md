## MODIFIED Requirements

### Requirement: 国际化与明暗主题

前端 MUST 支持中文与英文两种界面语言（经 `vue-i18n` 实现，UI 文案抽取为 locale key，`zh` 与 `en` 两套），并 MUST 支持明色与暗色两种主题；语言与主题的切换 MUST 全站生效（覆盖所有页面的 UI 文案与控件可读文案），且用户选择 MUST 被持久化（语言存 `localStorage`），刷新或重启容器后 MUST 保留。笔记正文与思维导图内容（LLM 产物原文）MUST NOT 被 i18n 改写，只翻译 UI 框架文案。

#### Scenario: 中英文切换全站生效

- **WHEN** 用户在设置页将界面语言从中文切换为英文（或反之）
- **THEN** 当前页面及导航至其他任一页面时，所有用户可见的 UI 文案 MUST 切换为对应语言（经 `$t` 渲染），MUST NOT 出现混用两种语言的残留文案；笔记正文与导图节点内容 MUST 保持产物原文不受影响

#### Scenario: 明暗主题切换并持久化

- **WHEN** 用户点击主题切换按钮将主题从明色切到暗色（或反之）后刷新页面
- **THEN** 全站 MUST 立即应用新主题，刷新后 MUST 保留用户选择的主题而非回退到默认

#### Scenario: 首次访问提供合理默认

- **WHEN** 用户首次在无任何偏好存档的情况下访问应用
- **THEN** 前端 MUST 提供一个确定的默认语言（中文）与默认主题（或跟随系统明暗偏好），MUST NOT 出现未渲染文案（显示裸 key）或无主题的中间态

#### Scenario: 语言选择持久化到本地

- **WHEN** 用户选择英文后关闭并重新打开浏览器
- **THEN** 应用 MUST 读取 `localStorage` 并以英文呈现 UI，MUST NOT 回退到中文默认
