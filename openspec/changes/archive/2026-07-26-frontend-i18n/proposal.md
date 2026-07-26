## Why

`web-frontend` spec「国际化与明暗主题」要求 UI 支持中英文切换、全站生效、持久化。当前所有 UI 文案（约 133 行中文）硬编码在 8 个组件，**无 i18n**，用户无法切换语言。用户要求在设置中切换整体 UI 中英文。

## What Changes

- 引入 `vue-i18n@9`（legacy global `$t` 模式，template 直接 `$t('key')`，无需每个组件 `useI18n`），新建 `src/i18n.js` + `locales/zh.js` + `locales/en.js`。
- `main.js` 注册 i18n 插件；`config` store 加 `locale`（默认 `zh`）+ `setLocale`（切 `i18n.global.locale` + 写 `localStorage` + 设 `document.lang`）。
- 全 UI 文案 → `$t('key')`：`App` / `Console` / `Note` / `Mindmap` / `Asr` / `History` / `Settings` / `TaskDetail` + `asr.js`。
- `Settings` 加语言切换 chip（中 / En）。

## Capabilities

### New Capabilities

（无。）

### Modified Capabilities

- `web-frontend`：修订「国际化与明暗主题」——明确经 `vue-i18n` + 设置页语言 chip 实现中英文全站切换，选择持久化到 `localStorage`。

## Impact

- **前端**：`+vue-i18n`；新建 `i18n.js` / `locales/zh.js` / `locales/en.js`；改 `main.js` / `stores/config.js` / 8 个 vue / `asr.js`。
- **spec**：`web-frontend` MODIFIED 国际化 Requirement。
- **测试**：`npm run build`；手动切语言验证全站文案。

## Non-goals

- **笔记正文 / 导图内容**翻译（只翻译 UI 文案；笔记/导图产物保持原文）。
- RTL 布局、动态远程语言包加载。
- 后端日志 / 错误信息的 i18n（后端中文错误保持）。
