# vid2note 设计系统(清晰普通版)

> 设计目标:**页面合理、排布清晰、内容可读**。不追求玻璃/渐变/炫技,回归标准现代 web UI。
> 实现见 `frontend/src/styles/app.css`;后续页面开发遵循本规范,避免风格漂移。

---

## 0. 设计原则

1. **清晰优先** —— 层级(标题/正文/辅助)、对比、分隔线清晰,文字一眼可读
2. **合理排布** —— 侧栏 + 主区 + 卡片,统一间距,对齐严谨
3. **实用克制** —— 实色卡片 + 标准组件 + 基础 hover,无玻璃/渐变/多层阴影炫技
4. **双主题** —— 亮(默认)/ 暗,token 切换,对比度达标

---

## 1. 设计 Token

### 1.1 颜色(亮 / 暗)
| token | 亮 | 暗 |
|---|---|---|
| `--bg` | `#f6f7f9` | `#111418` |
| `--card` | `#ffffff` | `#1a1d23` |
| `--card-2` | `#f3f4f6` | `#21252c` |
| `--text` | `#1f2937` | `#e5e7eb` |
| `--text-2` | `#4b5563` | `#9ca3af` |
| `--muted` | `#6b7280` | `#6b7280` |
| `--border` | `#e5e7eb` | `#2a2e36` |
| `--border-2` | `#d1d5db` | `#3a3f48` |
| `--accent` | `#2563eb` | `#3b82f6` |
| `--accent-soft` | `#eff6ff` | `#1e293b` |
| `--success` | `#16a34a` | `#16a34a` |
| `--danger` | `#dc2626` | `#dc2626` |

### 1.2 圆角 / 阴影 / 字体 / 间距
| 类别 | token | 值 |
|---|---|---|
| 圆角 | `--r-sm` / `--r` / `--r-lg` | `6px` / `8px` / `12px`(胶囊按钮/徽章用 `999px`) |
| 阴影 | `--shadow` | `0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.04)`(克制,仅浮起暗示) |
| focus | `--ring` | `0 0 0 3px rgba(37,99,235,.15)` |
| 字体 | `--font` | `-apple-system, "Segoe UI", "PingFang SC", system-ui, sans-serif` |
| 衬线 | `--serif` | `Georgia, "Songti SC", serif`(笔记标题) |
| 等宽 | `--mono` | `"SF Mono", ui-monospace, Menlo, monospace` |
| 过渡 | `--ease` | `.2s` |

---

## 2. 布局

```
┌─ titlebar(48px,实色 #fff,底部 1px 边)─────────────────┐
├─ sidebar(220px) ┬─ content(主区,卡片列表)─────────────┤
│  品牌            │  ┌ card ──────────────────────┐    │
│  导航(主控台/    │  │ 标题 + 内容                  │    │
│   历史/设置)      │  └────────────────────────────┘    │
│  引擎状态卡       │  ┌ card ─────────────────────┐    │
│                  │  │ ...                        │    │
└──────────────────┴──────────────────────────────┘
```

- **titlebar**:48px 高,实色 `--card` 背景,底部 1px `--border` 分隔
- **sidebar**:220px 宽,实色 `--card`,导航项 hover/active 高亮
- **content**:flex 1,`.scroll` 内边距 `24px 28px`,`.page` 最大 `900px` 居中
- **卡片**:垂直堆叠,`margin-bottom:14px`,清晰分隔

---

## 3. 组件库

### 3.1 卡片 `.card`
```html
<div class="card">…</div>
<div class="card pad">…</div>  <!-- 内边距大 -->
```
实色 `--card` 背景 + 1px `--border` + 8px 圆角 + 微阴影。**不用玻璃/渐变**。

### 3.2 按钮 `.btn`(实色,hover 色变,无 scale)
```html
<button class="btn">次级</button>
<button class="btn btn-primary">主按钮</button>
<button class="btn btn-ghost">幽灵</button>
<button class="btn btn-sm">小</button>
```
- `.btn`:白底 + 边,hover 变 `--card-2`
- `.btn-primary`:蓝实色,hover 加深
- `.btn-ghost`:透明,hover 浅底
- 全部 `white-space:nowrap`(不换行)

### 3.3 输入 `.input` / `.input-affix`
```html
<input class="input" placeholder="…">
<div class="input-affix"><span class="lead">🔗</span><input class="input"><span class="append"><button class="btn btn-primary">开始</button></span></div>
```
白底 + 边,focus 蓝光晕 `--ring`。

### 3.4 徽章 / chip / progress
- `.badge.running/.completed/.failed/.pending`:状态徽章,浅色底 + 状态色字,`nowrap`
- `.chip`:可选项,active 蓝实色
- `.progress > i`:进度条

### 3.5 表格 `.table` + 产物列 `.td-actions`
```html
<td class="td-actions"><button class="btn btn-sm">笔记</button> <button class="btn btn-sm">导图</button></td>
```
`.td-actions` = `flex row + nowrap`(产物按钮一行不竖排)。

### 3.6 流水线节点 `.pipeline-rail`
```html
<div class="pipeline-rail">
  <div class="pr-node done"><div class="pr-dot"></div><div class="pr-label">下载</div></div>
  <div class="pr-link done"></div>
  <div class="pr-node running">…</div>
</div>
```
节点状态:`pending`(灰)/ `running`(蓝 + pulse)/ `done`(绿)/ `failed`(红)。连接线 `done` 变绿。

### 3.7 笔记 `.note-wrap` + `.note-md`
```html
<div class="note-wrap"><div class="note-md" v-html="…"></div></div>
```
限宽 720px 居中,标题衬线,正文 16px / 1.8 行距,清晰阅读。

### 3.8 日志终端 `.log-term`
深色 `#1e1e1e` 底,等宽字体,日志行按级别着色(`.lt-ok/.lt-info/.lt-warn/.lt-err`)。

---

## 4. 交互

| 状态 | 实现 |
|---|---|
| hover | 背景色变(`--card-2` / 加深),**不用 scale / glass** |
| focus | 蓝光晕 `--ring`(输入/搜索) |
| active | 背景再深一档(`--border`) |
| disabled | `opacity:.5` + `not-allowed` |
| nav active | `--accent-soft` 底 + `--accent` 字 |

**过渡统一 `.2s`**。无炫技动效。

---

## 5. 暗主题

`[data-theme="dark"]` 切换 token(见 §1.1)。所有组件自动适配(用 token,不硬编码颜色)。切换持久化 `localStorage`。

---

## 6. do / don't

**do**
- ✅ 用 token(`var(--card)` 等),不硬编码颜色
- ✅ 实色卡片 + 细边 + 微阴影(清晰分隔)
- ✅ 文字层级清晰(text/text-2/muted/muted-2)
- ✅ 胶囊/按钮 `white-space:nowrap`(不换行)
- ✅ 产物/操作列用 `.td-actions`(flex row)
- ✅ 间距统一(16/24/28)
- ✅ 暗 用 token 自动适配

**don't**
- ❌ 玻璃(`backdrop-filter`)/ 渐变背景 / 多层 inset 阴影(已弃,违清晰原则)
- ❌ hover scale / 炫技动效
- ❌ 硬编码颜色(用 token)
- ❌ 胶囊/按钮换行(必 nowrap)
- ❌ 产物列竖排(用 `.td-actions` flex row)

---

## 7. 新增页面/组件清单(后续开发对照)

新建页面时:
1. 用 `.page` 包裹(最大 900px 居中)
2. 内容用 `.card` 分区
3. 表单用 `.input` / `.input-affix` + `.btn`
4. 列表用 `.table` 或 `.card` 堆叠 + `.stagger`(进场)
5. 状态用 `.badge` / `.chip`
6. 颜色全用 token,暗 自动适配
7. 胶囊/按钮 `nowrap`,操作列 `.td-actions`

新增组件时:遵循 token + 实色 + 细边 + 微阴影 + `.2s` 过渡,不引玻璃/渐变。
