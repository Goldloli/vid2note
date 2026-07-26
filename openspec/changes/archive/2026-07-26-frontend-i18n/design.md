## Context

8 个组件约 133 行中文 UI 文案硬编码。需引入 i18n 并全站替换。

## Goals / Non-Goals

**Goals:** vue-i18n 全站中英文；设置页切换；持久化；首次默认中文。

**Non-Goals:** 笔记/导图内容翻译；RTL；后端文案 i18n。

## Decisions

### D1 vue-i18n legacy global `$t`（非 composition `useI18n`）

- **Why**：template 直接 `{{ $t('nav.console') }}`，无需每个 `<script setup>` 引入 `useI18n`，改动最小、最稳。
- **Alt**：composition `useI18n`（每个组件多 2 行，133 行文案时繁琐）。

### D2 文案按页面分 key 命名空间

- `nav.*`（侧栏）、`console.*`、`note.*`、`mindmap.*`、`asr.*`、`history.*`、`settings.*`、`task.*`、`common.*`（复制/保存/取消等通用）。`zh.js` / `en.js` 同 key 结构。

### D3 locale 持久化 + 应用

- `config` store：`locale` 初始读 `localStorage.getItem('locale') || 'zh'`；`setLocale(v)` → `i18n.global.locale.value = v` + `localStorage.setItem('locale', v)` + `document.documentElement.lang = v`。
- `main.js`：`createI18n({ legacy: true, locale: 初始, fallbackLocale: 'zh', messages })` + `app.use(i18n)`。
- `Settings` 语言 chip 调 `config.setLocale`。

### D4 笔记/导图内容不翻译

- `Note.vue` 的正文（v-html marked 笔记）、`Mindmap.vue` 的导图节点文本 = 产物原文，**不进 i18n**。只 i18n 该页的 UI 框架文案（标题、按钮、提示）。

## Risks / Trade-offs

- **[133 行文案逐条替换易漏]** → 按 8 文件逐个替换 + build 验证；遗漏项会显示 key 名（易发现）。
- **[en 翻译准确性]** → 技术词保留英文（ASR/LLM/PDF/SSE），功能词意译。

## Migration Plan

前端增量，无数据迁移。回滚：移除 i18n.js/locales + 还原 vue 文案。
