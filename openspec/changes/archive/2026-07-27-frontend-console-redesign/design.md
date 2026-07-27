## Context

Console.vue 当前：URL 输入框（含「开始」按钮）+ 下方「上传本地视频/音频」label + 引擎 chip。onFile 选文件后**自动 create + 跳转**（无法先配引擎）。

## Goals / Non-Goals

**Goals:** 网络视频 / 本地文件两区并列同等；引擎共享；手动开始（选文件不自动提交）。

**Non-Goals:** 拖拽上传；引擎选择项内容变更；统计/列表区改动。

## Decisions

### D1 两区并列（flex 两卡片，等宽）

```
┌─ 网络视频 ─────────┐ ┌─ 本地文件 ────────┐
│ [URL 输入框]       │ │ [选择文件] 按钮   │
│ 粘贴视频链接…      │ │ 已选: xxx.mp4    │
└────────────────────┘ └──────────────────┘
```
窄屏可堆叠（v1 简单 flex-wrap）。

### D2 引擎选择共享（两区下方一行）

ASR chip / LLM select / 语言 chip / 截图 chip —— 一行，两区共用（不重复）。

### D3 手动开始（选文件不自动提交）

- `form.file` 暂存选中的 File（onFile 只设 `form.file = f` + 显示文件名，**不 create**）。
- 「开始」按钮：URL 非空 → FormData(source_url)；否则 form.file → FormData(file)；都没 → 提示。
- 提交后清空 URL / file。

### D4 「开始」单按钮（智能）

一个「开始」按钮（替代原 URL 框内的 append 按钮 + 上传自动）。点后按填的内容提交。

## Risks / Trade-offs

- **[用户两区都填]** → URL 优先（文件被忽略 + 提示）；或拒绝。v1：URL 优先，文件忽略。
- **[选大文件暂存内存]** → File 对象引用（不读内容），轻量；提交时 FormData 流式上传。

## Migration Plan

前端增量，无数据迁移。回滚：还原 Console.vue。
