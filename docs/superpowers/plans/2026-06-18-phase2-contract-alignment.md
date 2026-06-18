# Phase 2: 前后端契约对齐 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 review 发现的 6 个 Critical 前后端契约 bug，让桌面端 UI 真正可用：任务详情能显示产物、思维导图能渲染、重跑能真正重跑、提交任务能带 mindmap 参数、设置页的保留策略能被后端接受。

**Architecture:** 每个任务都是「改后端 + 改前端」的双向对齐，让两者的数据结构和行为一致。后端改动小而聚焦（加字段、加逻辑、加端点），前端改动修正字段路径和参数传递。不引入新依赖。

**Tech Stack:** FastAPI（server）、Vue 3（desktop renderer）、axios。

**前提：** Phase 1 已完成（测试套件绿灯，`asrtools.py` 已删除）。`.venv/bin/python` 可用，`cd desktop && npx vite build` 可用。

---

## 文件结构（改动清单）

**后端（server/core）:**
- Modify: `server/src/vid2note_server/api/tasks.py` — `rerun_task` 真正重跑（重置节点状态 + 删除下游产物 + 重新入队 + 发事件）
- Modify: `server/src/vid2note_server/api/config.py` — `UpdateConfigRequest` 接受 retention/language/advanced 字段
- Modify: `core/src/vid2note_core/storage/task_repo.py` — 加 `reset_task_for_rerun` 方法
- Modify: `core/src/vid2note_core/worker.py` — 提交任务时读 `export_mindmap` 并传入 ctx.config

**前端（desktop）:**
- Modify: `desktop/src/renderer/views/TaskDetail.vue` — 修正 artifacts 字段路径（`res.artifacts` 嵌套）
- Modify: `desktop/src/renderer/views/Mindmap.vue` — 用 mermaid 库真正渲染（替换死的 tryRenderMermaid）
- Modify: `desktop/src/renderer/api/task.js` — `createTask` 传递 `export_mindmap` 和 provider 选项
- Modify: `desktop/src/renderer/views/Home.vue` — 提交时带 `export_mindmap: true`
- Modify: `desktop/src/renderer/views/Settings.vue` — 发送 retention/language 字段、修正 ASR key 测试目标
- Modify: `desktop/index.html` — 引入 mermaid.js CDN

---

## Task 1: 修正 TaskDetail.vue 的 artifacts 字段路径（Critical）

后端 `GET /process/result/{id}` 返回 `{task_id, status, progress, artifacts: {...}}`，但 `TaskDetail.vue:137` 把整个响应赋给 `artifacts.value`，模板却读 `artifacts.srt`（缺一层 `.artifacts` 嵌套），导致产物 tab 永远空白。

**Files:**
- Modify: `desktop/src/renderer/views/TaskDetail.vue:137`

- [ ] **Step 1: 定位 `_loadResult`**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && grep -n "_loadResult\|artifacts.value\|artifacts.srt\|artifacts.markdown\|artifacts.mindmap" desktop/src/renderer/views/TaskDetail.vue`

- [ ] **Step 2: 修正赋值**

把 `artifacts.value = await getProcessResult(props.id)`（返回 `{task_id,status,progress,artifacts:{...}}`）改为只取内层 `artifacts`：

```javascript
async function _loadResult() {
  try {
    const res = await getProcessResult(props.id)
    // 后端返回 {artifacts: {srt, markdown, mindmap}}，这里只取内层
    artifacts.value = res.artifacts || res || {}
  } catch (e) {}
}
```

- [ ] **Step 3: 验证模板字段名与后端产物键一致**

后端 `process.py:120-135` 的 artifact 键名是 `srt`/`markdown`/`mindmap`（来自节点名映射）。确认模板读的是 `artifacts.srt` / `artifacts.markdown` / `artifacts.mindmap`（TaskDetail.vue 约 35-37 行）。若不一致则对齐到 `srt`/`markdown`/`mindmap`。

- [ ] **Step 4: 构建验证**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note/desktop && npx vite build 2>&1 | tail -3`
Expected: 构建成功，无错误。

- [ ] **Step 5: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add desktop/src/renderer/views/TaskDetail.vue
git commit -m "fix(desktop): TaskDetail 读取产物时解包 res.artifacts（修复产物 tab 永远空白）"
```

---

## Task 2: 让 rerun_task 真正重跑任务（Critical）

当前 `POST /tasks/{id}/rerun` 只把 status 改回 PENDING，不重置节点、不删产物、不重新入队，导致任务永远卡住。需要：(1) 删除 from_node 下游产物；(2) 重置该节点及其下游的 task_nodes 状态为 PENDING；(3) 重置 task 的 progress/error；(4) 发 `task.rerun` 事件。

**Files:**
- Modify: `core/src/vid2note_core/storage/task_repo.py` — 加 `reset_task_for_rerun`
- Modify: `server/src/vid2note_server/api/tasks.py` — `rerun_task` 调用上述方法

- [ ] **Step 1: 在 TaskRepository 加 reset_task_for_rerun 方法**

在 `task_repo.py` 合适位置（如 `update_node` 方法之后）添加：

```python
def reset_task_for_rerun(self, task_id: str, from_node: str | None = None) -> None:
    """重置任务以重跑：清零进度、清错误、把状态改回 PENDING。

    from_node 为 None 时重跑整个 pipeline；否则只重置 from_node 及其下游节点状态
    （产物删除由 ArtifactStore.delete_downstream 负责，调用方处理）。
    """
    from vid2note_core.types import TaskStatus

    with self.db.get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, progress = 0, error_message = NULL, "
            "current_step = NULL WHERE task_id = ?",
            (TaskStatus.PENDING.value, task_id),
        )
        if from_node:
            # 重置 from_node 及下游节点为 PENDING
            downstream = self._node_and_downstream(from_node)
            if downstream:
                placeholders = ",".join("?" * len(downstream))
                conn.execute(
                    f"UPDATE task_nodes SET status = 'pending', "
                    f"error = NULL, started_at = NULL, completed_at = NULL "
                    f"WHERE task_id = ? AND node_name IN ({placeholders})",
                    [task_id, *downstream],
                )
        else:
            conn.execute(
                "UPDATE task_nodes SET status = 'pending', error = NULL, "
                "started_at = NULL, completed_at = NULL WHERE task_id = ?",
                (task_id,),
            )
        conn.commit()

def _node_and_downstream(self, from_node: str) -> list[str]:
    """返回 from_node 及其拓扑下游的节点名列表。"""
    order = ["download", "extract_audio", "transcribe", "organize", "mindmap", "cleanup"]
    try:
        idx = order.index(from_node)
    except ValueError:
        return []
    return order[idx:]
```

- [ ] **Step 2: 重写 rerun_task 端点**

替换 `tasks.py` 中的 `rerun_task`（约 65-72 行）：

```python
from vid2note_core.events.bus import TaskEvent, get_event_bus
from vid2note_core.storage.artifact_store import ArtifactStore


@router.post("/tasks/{task_id}/rerun")
async def rerun_task(task_id: str, from_node: str | None = None):
    from vid2note_core.types import TaskId
    if not TaskId.is_valid(task_id):
        raise HTTPException(404, "任务不存在")

    repo = TaskRepository()
    task = repo.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    # 1. 删除 from_node 下游产物（若有）
    if from_node:
        ArtifactStore().delete_downstream(task_id, from_node)

    # 2. 重置任务和节点状态
    repo.reset_task_for_rerun(task_id, from_node)

    # 3. 发事件通知前端
    get_event_bus().publish(
        TaskEvent(
            task_id=task_id,
            event_type="task.rerun",
            message=f"已触发重跑（from {from_node or 'start'}）",
            progress=0,
        )
    )

    return {"task_id": task_id, "status": "pending", "message": "已触发重跑"}
```

- [ ] **Step 3: 写集成测试**

在 `server/tests/integration/test_tasks.py` 增加：

```python
def test_rerun_resets_status_and_progress(client, sample_task):
    """rerun 后任务应回到 pending、progress=0。"""
    # 先把任务标记为 completed
    TaskRepository().update(sample_task, status=TaskStatus.COMPLETED, progress=100)

    resp = client.post(f"/api/v1/tasks/{sample_task}/rerun")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"

    task = TaskRepository().get(sample_task)
    assert task.status == TaskStatus.PENDING
    assert task.progress == 0


def test_rerun_unknown_task_returns_404(client):
    resp = client.post("/api/v1/tasks/task_000000000000/rerun")
    assert resp.status_code == 404


def test_rerun_from_node_deletes_downstream(client, sample_task):
    """rerun from_node=transcribe 应删除 organize/mindmap/cleanup 产物。"""
    store = ArtifactStore()
    store.write_artifact(sample_task, "transcribe", "srt_file", b"srt")
    store.write_artifact(sample_task, "organize", "markdown_file", b"md")
    store.write_artifact(sample_task, "mindmap", "mindmap_file", b"mm")

    client.post(f"/api/v1/tasks/{sample_task}/rerun", json={"from_node": "transcribe"})

    # transcribe 的产物应保留，organize/mindmap 应删除
    assert store.exists(sample_task, "transcribe", "srt_file")
    assert not store.exists(sample_task, "organize", "markdown_file")
    assert not store.exists(sample_task, "mindmap", "mindmap_file")
```

- [ ] **Step 4: 运行测试**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest server/tests/integration/test_tasks.py -v 2>&1 | tail -15`
Expected: 新增 3 个测试 passed。

- [ ] **Step 5: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add core/src/vid2note_core/storage/task_repo.py server/src/vid2note_server/api/tasks.py server/tests/integration/test_tasks.py
git commit -m "fix(server): rerun_task 真正重置节点状态+删除下游产物+发事件（修复重跑空操作）"
```

---

## Task 3: createTask 传递 export_mindmap 和 provider 选项（Critical）

当前 `api/task.js` 只发 `{video_url}`，`export_mindmap` 永远 false，导致思维导图从不生成。需要让前端在提交时带 `export_mindmap: true` 和用户在设置里选的 provider。

**Files:**
- Modify: `desktop/src/renderer/api/task.js`
- Modify: `desktop/src/renderer/views/Home.vue`（提交调用处）

- [ ] **Step 1: 改 createTask 接受并透传完整选项**

```javascript
import request from './request'

// 任务 API
export const createTask = (videoUrl, opts = {}) =>
  request.post('/tasks', {
    video_url: videoUrl,
    export_mindmap: opts.export_mindmap ?? true,
    asr_provider: opts.asr_provider,
    llm_provider: opts.llm_provider,
    ...opts,
  })

export const listTasks = () => request.get('/tasks')

export const getTask = (taskId) => request.get(`/tasks/${taskId}`)

export const rerunTask = (taskId, fromNode = null) =>
  request.post(`/tasks/${taskId}/rerun`, { from_node: fromNode })
```

- [ ] **Step 2: 确认 Home.vue 提交处已用 createTask**

检查 `Home.vue` 约 120-130 行的 `submit` 函数，确认调用 `createTask(url, {...})`。若当前是 `createTask(url)` 无第二参，则思维导图默认 true 已生效（Step 1 的默认值）。

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && grep -n "createTask" desktop/src/renderer/views/Home.vue desktop/src/renderer/stores/task.js`

- [ ] **Step 3: 确认 worker 读 export_mindmap**

检查 `core/src/vid2note_core/worker.py` 在构造 `ctx.config` 时是否包含 `export_mindmap`。当前 worker 读 `task.export_mindmap`（TaskRecord 字段）。确认 `RealMindmapNode` 会跳过生成当 `export_mindmap=False`。

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && grep -n "export_mindmap\|mindmap" core/src/vid2note_core/worker.py core/src/vid2note_core/pipeline/real_nodes.py | head`

若 worker 未传 export_mindmap 到 ctx.config，在 worker `_process` 的 ctx.config dict 里加一行 `"export_mindmap": task.export_mindmap,`。

- [ ] **Step 4: 构建验证**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note/desktop && npx vite build 2>&1 | tail -3`
Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add desktop/src/renderer/api/task.js desktop/src/renderer/views/Home.vue core/src/vid2note_core/worker.py
git commit -m "fix(contract): createTask 默认 export_mindmap=true，确保思维导图被生成"
```

---

## Task 4: 让思维导图视图真正渲染 Mermaid（Critical）

`Mindmap.vue` 的 `tryRenderMermaid` 是死代码（mermaid 未加载、用的是已废弃的 callback API）。需要：(1) index.html 引入 mermaid CDN；(2) 用 mermaid v10+ 的 Promise API 渲染。

**Files:**
- Modify: `desktop/index.html` — 引入 mermaid
- Modify: `desktop/src/renderer/views/Mindmap.vue` — 重写渲染逻辑

- [ ] **Step 1: 在 index.html 引入 mermaid**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && cat desktop/index.html`

在 `</body>` 前加：
```html
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs'
  mermaid.initialize({ startOnLoad: false, theme: 'neutral' })
  window.mermaid = mermaid
</script>
```

- [ ] **Step 2: 重写 Mindmap.vue 的渲染逻辑**

替换 `renderedSvg` computed 和 `tryRenderMermaid`（Mindmap.vue:41-47, 65-69）为基于 Promise 的异步渲染：

```vue
<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getProcessResult } from '../api/process'

const route = useRoute()
const id = computed(() => route.params.id || '')
const mermaidText = ref('')
const renderedSvg = ref('')
const loading = ref(true)
const renderError = ref('')

const outline = computed(() => {
  if (!mermaidText.value) return []
  const lines = mermaidText.value.split('\n')
  const result = []
  for (const line of lines) {
    const m = line.match(/^(\s*)(.+)$/)
    if (m && m[2].trim() && !m[2].trim().startsWith('mindmap')) {
      result.push({ depth: Math.min(4, Math.floor(m[1].length / 2) + 1), text: m[2].trim().replace(/\(.*?\)|\[.*?\]|\{.*?\}/g, '') })
    }
  }
  return result
})

function escapeHtml(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }

async function renderMermaid() {
  if (!mermaidText.value) return
  renderError.value = ''
  // mermaid 未加载（离线）时回退为源码显示
  if (typeof window === 'undefined' || !window.mermaid) {
    renderedSvg.value = `<div class="mm-fallback"><pre>${escapeHtml(mermaidText.value)}</pre></div>`
    return
  }
  try {
    // mermaid v10+ 返回 Promise，不再用 callback
    const { svg } = await window.mermaid.render('mm-svg-' + Date.now(), mermaidText.value)
    renderedSvg.value = svg
  } catch (e) {
    renderError.value = String(e)
    renderedSvg.value = `<div class="mm-fallback"><pre>${escapeHtml(mermaidText.value)}</pre></div>`
  }
}

async function copy() { try { await navigator.clipboard.writeText(mermaidText.value) } catch (e) {} }
function exportMmd() { const blob = new Blob([mermaidText.value], { type: 'text/plain' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `mindmap-${id.value}.mmd`; a.click() }

onMounted(async () => {
  try {
    const res = await getProcessResult(id.value)
    mermaidText.value = res.artifacts?.mindmap || ''
    if (mermaidText.value) await renderMermaid()
  } catch (e) {}
  loading.value = false
})

watch(mermaidText, () => { renderMermaid() })
</script>
```

注意模板里 `v-html="renderedSvg"` 保持不变，但 `renderedSvg` 现在是 `ref`（不是 computed）。模板改为 `v-html="renderedSvg"`（去掉 `.value`，Vue 自动解包）。

- [ ] **Step 3: 构建验证**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note/desktop && npx vite build 2>&1 | tail -3`
Expected: 构建成功。

- [ ] **Step 4: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add desktop/index.html desktop/src/renderer/views/Mindmap.vue
git commit -m "fix(desktop): 思维导图改用 mermaid v10 Promise API 真正渲染（修复死代码）"
```

---

## Task 5: 修复 Settings.vue 保留策略字段被后端丢弃（Critical）

`PUT /config` 的 `UpdateConfigRequest` 只接受 `llm_provider`/`asr_provider`，Settings.vue 发送的 `keep_video`/`keep_audio`/`keep_srt`/`language` 被 Pydantic 静默丢弃。需要扩展后端请求模型。

**Files:**
- Modify: `server/src/vid2note_server/api/config.py` — `UpdateConfigRequest` 加字段
- Modify: `desktop/src/renderer/views/Settings.vue` — 修正 ASR key 测试目标

- [ ] **Step 1: 扩展 UpdateConfigRequest**

查看 `config.py` 当前 `UpdateConfigRequest`（约 33-37 行），改为：

```python
class UpdateConfigRequest(BaseModel):
    llm_provider: str | None = None
    asr_provider: str | None = None
    # 保留策略（Settings.vue "保留策略" tab）
    keep_video: bool | None = None
    keep_audio: bool | None = None
    keep_srt: bool | None = None
    keep_markdown: bool | None = None
    keep_mindmap: bool | None = None
    # 处理选项
    language: str | None = None
    mindmap_format: str | None = None
```

- [ ] **Step 2: update_config 持久化新字段**

在 `update_config` 函数里（约 40-54 行），把新字段写入 AppConfig：

```python
@router.put("/config")
async def update_config(req: UpdateConfigRequest):
    cfg = ConfigManager().load()
    if req.llm_provider is not None:
        cfg.llm_provider = req.llm_provider
    if req.asr_provider is not None:
        cfg.asr_provider = req.asr_provider
    if req.keep_video is not None:
        cfg.retention.keep_video = req.keep_video
    if req.keep_audio is not None:
        cfg.retention.keep_audio = req.keep_audio
    if req.keep_srt is not None:
        cfg.retention.keep_srt = req.keep_srt
    if req.keep_markdown is not None:
        cfg.retention.keep_markdown = req.keep_markdown
    if req.keep_mindmap is not None:
        cfg.retention.keep_mindmap = req.keep_mindmap
    if req.language is not None:
        cfg.processing.language = req.language
    if req.mindmap_format is not None:
        cfg.processing.mindmap_format = req.mindmap_format
    ConfigManager().save(cfg)
    return _safe_config_dump(cfg)
```

（确认 `RetentionConfig`/`ProcessingConfig` 有这些字段——见 `core/config/models.py`，若无则在 Phase 2 补。）

- [ ] **Step 3: 修正 Settings.vue ASR key 测试标签**

`Settings.vue:26-27` 把 ASR key 输入框标成 "asrtools-b 云端识别密钥"，但 `verifyKey()` 测的是 LLM provider。由于 bk_asr 不需要 key，应把 ASR key 区块改为说明文字：

```vue
<!-- ASR 密钥区块改为说明 -->
<div class="form-row">
  <label>ASR 密钥</label>
  <div class="muted mono-sm">当前 ASR（asrtools-b）为免费云端接口，无需 API 密钥。</div>
</div>
```

- [ ] **Step 4: 构建验证 + 测试**

Run:
```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/python -m pytest server/tests/ -q 2>&1 | tail -3
cd desktop && npx vite build 2>&1 | tail -3
```
Expected: 测试 passed，构建成功。

- [ ] **Step 5: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add server/src/vid2note_server/api/config.py desktop/src/renderer/views/Settings.vue
git commit -m "fix(config): UpdateConfigRequest 接受 retention/language/mindmap_format（修复设置页字段被丢弃）"
```

---

## Task 6: 全量回归 + 端到端验证

**Files:** 无

- [ ] **Step 1: 后端全量测试**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest core/tests server/tests -q 2>&1 | tail -5`
Expected: all passed。

- [ ] **Step 2: 启动后端跑真实任务验证产物 tab + 思维导图**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
set -a && source .env && set +a
.venv/bin/python -m uvicorn vid2note_server.main:app --port 8765 &
sleep 4
curl -s -X POST http://127.0.0.1:8765/api/v1/tasks -H "Content-Type: application/json" \
  -d '{"video_url":"https://www.bilibili.com/video/BV1KTEd6DEfN","export_mindmap":true,"asr_provider":"asrtools-b","llm_provider":"qwen"}'
# 轮询至 completed
# 然后 curl /api/v1/process/result/<task_id> 确认 artifacts.mindmap 非空
```

- [ ] **Step 3: 前端构建并验证产物显示**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note/desktop
npx vite build
npx electron-builder --mac dmg --publish never
```
安装后打开 app，进入任务详情，确认「笔记预览」「思维导图」tab 有内容、思维导图渲染为 SVG 图形（非源码）。

- [ ] **Step 4: 提示用户验证**

告知用户重新构建的 app 位置，请其确认：(a) 任务详情三个 tab 有内容；(b) 思维导图页渲染为图形；(c) 设置页保留策略可保存；(d) 重跑按钮能让任务重新执行。

---

## Self-Review

**1. Spec coverage:**
- ✅ TaskDetail artifacts 路径错位 → Task 1
- ✅ rerun 空操作 → Task 2
- ✅ export_mindmap 未发送 → Task 3
- ✅ Mermaid 渲染失效 → Task 4
- ✅ 配置字段被丢弃 → Task 5
- ✅ 端到端验证 → Task 6
- 注：Note.vue markdown 渲染器 bug、provider chip 硬编码是 High（非 Critical），留后续。

**2. Placeholder scan:** 每步有完整代码。Task 5 Step 2 引用 `RetentionConfig`/`ProcessingConfig` 字段——已在 review 中确认 `config/models.py` 存在，若缺会在执行时发现并补。

**3. Type consistency:** `reset_task_for_rerun` 签名在 Task 2 Step 1 和 Step 2 调用一致。`export_mindmap` 字段从 api/task.js → CreateTaskRequest → TaskRecord → worker ctx.config 贯穿一致。
