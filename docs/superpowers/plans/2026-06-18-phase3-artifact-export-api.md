# Phase 3: 产物下载/导出 API 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后端目前没有任何 `FileResponse` 端点——用户无法下载生成的 `.md`/`.srt`/`.mmd` 文件。本阶段新增：(1) 列出任务所有产物的端点；(2) 单文件下载端点（正确 Content-Type）；(3) 一键打包导出端点；(4) 前端「导出」按钮调用这些端点。

**Architecture:** 复用现有 `ArtifactStore.list_artifacts` / `read_artifact`（当前仅被 process.py 间接用了一次）。新增 `api/artifacts.py` router，提供 list/download/export-all 三个端点。前端在 TaskDetail/Note/Mindmap 页加「下载」按钮。

**Tech Stack:** FastAPI `FileResponse` / `StreamingResponse`，`zipfile`（标准库）。

**前提：** Phase 1、Phase 2 已完成。

---

## 文件结构（改动清单）

**后端:**
- Create: `server/src/vid2note_server/api/artifacts.py` — 产物下载 router
- Modify: `server/src/vid2note_server/main.py` — 注册 artifacts router
- Create: `server/tests/integration/test_artifacts.py` — 端点测试

**前端:**
- Modify: `desktop/src/renderer/api/task.js` — 加下载 helper（触发浏览器下载）
- Modify: `desktop/src/renderer/views/Note.vue` / `Mindmap.vue` / `TaskDetail.vue` — 加下载/导出按钮

---

## Task 1: 新增产物列表端点 GET /tasks/{id}/artifacts

**Files:**
- Create: `server/src/vid2note_server/api/artifacts.py`

- [ ] **Step 1: 写 artifacts router（list + download + export 合在一个文件）**

```python
"""产物下载/导出 API"""

import zipfile
from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from vid2note_core.storage.artifact_store import ArtifactStore
from vid2note_core.types import TaskId
from vid2note_core.storage.task_repo import TaskRepository

router = APIRouter(prefix="/api/v1", tags=["artifacts"])

# artifact 键 → (文件名, Content-Type) 映射
# 键名来自 ArtifactStore 的 f"{node}_{name}" 命名约定
_ARTIFACT_META = {
    "transcribe_srt_file": ("transcript.srt", "application/x-subrip", "srt"),
    "organize_markdown_file": ("note.md", "text/markdown; charset=utf-8", "markdown"),
    "mindmap_mindmap_file": ("mindmap.mmd", "text/plain; charset=utf-8", "mindmap"),
}


@router.get("/tasks/{task_id}/artifacts")
async def list_artifacts(task_id: str):
    """列出任务的所有产物文件。"""
    if not TaskId.is_valid(task_id):
        raise HTTPException(404, "任务不存在")
    repo = TaskRepository()
    if not repo.get(task_id):
        raise HTTPException(404, "任务不存在")

    store = ArtifactStore()
    items = []
    for path in store.list_artifacts(task_id):
        meta = _ARTIFACT_META.get(path.name)
        items.append(
            {
                "key": path.name,
                "name": meta[0] if meta else path.name,
                "content_type": meta[1] if meta else "application/octet-stream",
                "type": meta[2] if meta else "unknown",
                "size": path.stat().st_size,
            }
        )
    return {"task_id": task_id, "artifacts": items}
```

- [ ] **Step 2: 注册 router**

在 `main.py` 的 router 注册区（约 30-31 行）加：

```python
from vid2note_server.api.artifacts import router as artifacts_router
app.include_router(artifacts_router)
```

- [ ] **Step 3: 写测试**

`server/tests/integration/test_artifacts.py`:

```python
"""测试产物下载/导出 API"""

from vid2note_core.storage.artifact_store import ArtifactStore


def test_list_artifacts(client, sample_task):
    """列出产物应返回文件名、类型、大小。"""
    store = ArtifactStore()
    store.write_artifact(sample_task, "organize", "markdown_file", b"# 笔记\n正文")

    resp = client.get(f"/api/v1/tasks/{sample_task}/artifacts")
    assert resp.status_code == 200
    data = resp.json()
    names = [a["name"] for a in data["artifacts"]]
    assert "note.md" in names
    md = next(a for a in data["artifacts"] if a["name"] == "note.md")
    assert md["type"] == "markdown"
    assert md["size"] == len("# 笔记\n正文")


def test_list_artifacts_unknown_task_404(client):
    resp = client.get("/api/v1/tasks/task_000000000000/artifacts")
    assert resp.status_code == 404


def test_list_artifacts_invalid_id_404(client):
    resp = client.get("/api/v1/tasks/not-a-task/artifacts")
    assert resp.status_code == 404
```

- [ ] **Step 4: 运行测试**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note && .venv/bin/python -m pytest server/tests/integration/test_artifacts.py -v 2>&1 | tail -10`
Expected: 3 passed。

- [ ] **Step 5: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add server/src/vid2note_server/api/artifacts.py server/src/vid2note_server/main.py server/tests/integration/test_artifacts.py
git commit -m "feat(server): 新增 GET /tasks/{id}/artifacts 列出任务产物"
```

---

## Task 2: 新增单文件下载端点 GET /tasks/{id}/artifacts/{key}

返回正确的 Content-Type 和 Content-Disposition（附件下载），支持二进制（如 xmind）。

**Files:**
- Modify: `server/src/vid2note_server/api/artifacts.py`

- [ ] **Step 1: 加 download 端点**

在 `artifacts.py` 追加：

```python
@router.get("/tasks/{task_id}/artifacts/{key}")
async def download_artifact(task_id: str, key: str):
    """下载单个产物文件（返回原始字节 + 正确 Content-Type）。"""
    if not TaskId.is_valid(task_id):
        raise HTTPException(404, "任务不存在")
    repo = TaskRepository()
    if not repo.get(task_id):
        raise HTTPException(404, "任务不存在")

    store = ArtifactStore()
    path = store._task_dir(task_id) / "artifacts" / key
    if not path.exists():
        raise HTTPException(404, "产物不存在")

    data = path.read_bytes()
    meta = _ARTIFACT_META.get(key)
    filename = meta[0] if meta else key
    content_type = meta[1] if meta else "application/octet-stream"

    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 2: 加测试**

```python
def test_download_artifact(client, sample_task):
    """下载 markdown 产物应返回正确内容和 Content-Type。"""
    content = "# 标题\n\n正文内容"
    ArtifactStore().write_artifact(sample_task, "organize", "markdown_file", content.encode())

    resp = client.get(f"/api/v1/tasks/{sample_task}/artifacts/organize_markdown_file")
    assert resp.status_code == 200
    assert resp.content.decode() == content
    assert "text/markdown" in resp.headers["content-type"]
    assert 'attachment; filename="note.md"' in resp.headers["content-disposition"]


def test_download_artifact_not_found(client, sample_task):
    resp = client.get(f"/api/v1/tasks/{sample_task}/artifacts/nonexistent_file")
    assert resp.status_code == 404
```

- [ ] **Step 3: 运行测试 + Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/python -m pytest server/tests/integration/test_artifacts.py -v 2>&1 | tail -5
git add server/src/vid2note_server/api/artifacts.py server/tests/integration/test_artifacts.py
git commit -m "feat(server): 新增 GET /tasks/{id}/artifacts/{key} 单文件下载"
```

---

## Task 3: 新增一键打包导出端点 GET /tasks/{id}/export

把所有产物打成 zip 下载。

**Files:**
- Modify: `server/src/vid2note_server/api/artifacts.py`

- [ ] **Step 1: 加 export 端点**

```python
@router.get("/tasks/{task_id}/export")
async def export_all_artifacts(task_id: str):
    """把任务所有产物打包为 zip 下载。"""
    if not TaskId.is_valid(task_id):
        raise HTTPException(404, "任务不存在")
    repo = TaskRepository()
    if not repo.get(task_id):
        raise HTTPException(404, "任务不存在")

    store = ArtifactStore()
    files = store.list_artifacts(task_id)
    if not files:
        raise HTTPException(404, "任务暂无产物")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            meta = _ARTIFACT_META.get(path.name)
            arcname = meta[0] if meta else path.name
            zf.writestr(arcname, path.read_bytes())
    buf.seek(0)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="vid2note-{task_id}.zip"'},
    )
```

- [ ] **Step 2: 加测试**

```python
def test_export_all_zip(client, sample_task):
    """导出 zip 应包含所有产物。"""
    store = ArtifactStore()
    store.write_artifact(sample_task, "organize", "markdown_file", b"# md")
    store.write_artifact(sample_task, "transcribe", "srt_file", b"srt content")

    resp = client.get(f"/api/v1/tasks/{sample_task}/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    import zipfile
    from io import BytesIO
    zf = zipfile.ZipFile(BytesIO(resp.content))
    names = zf.namelist()
    assert "note.md" in names
    assert "transcript.srt" in names


def test_export_empty_task_404(client, sample_task):
    """无产物时导出应 404。"""
    resp = client.get(f"/api/v1/tasks/{sample_task}/export")
    assert resp.status_code == 404
```

- [ ] **Step 3: 运行测试 + Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
.venv/bin/python -m pytest server/tests/integration/test_artifacts.py -v 2>&1 | tail -5
git add server/src/vid2note_server/api/artifacts.py server/tests/integration/test_artifacts.py
git commit -m "feat(server): 新增 GET /tasks/{id}/export 一键打包导出 zip"
```

---

## Task 4: 前端加下载/导出按钮

**Files:**
- Modify: `desktop/src/renderer/api/task.js`
- Modify: `desktop/src/renderer/views/TaskDetail.vue` / `Note.vue` / `Mindmap.vue`

- [ ] **Step 1: 在 api/task.js 加下载 helper**

```javascript
// 触发浏览器下载指定产物
export const downloadArtifact = async (taskId, key) => {
  const baseURL = (await import('./request')).default.defaults.baseURL
  const url = `${baseURL}/api/v1/tasks/${taskId}/artifacts/${key}`
  // Electron 渲染进程可用 <a download> 触发下载
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  a.click()
}

// 一键导出全部产物 zip
export const exportAllArtifacts = (taskId) => {
  // 在新窗口打开，浏览器会按 Content-Disposition 下载
  window.open(`${baseURL}/api/v1/tasks/${taskId}/export`, '_blank')
}
```

（`baseURL` 需从 request.js 的已解析值取；若 request.js 未导出 baseURL，改用 `await window.electronAPI.getBackendUrl()` 拼接。）

- [ ] **Step 2: TaskDetail.vue 加「导出全部」按钮**

在产物 tab 区域（约 35-37 行附近）加：

```vue
<button class="btn btn-sm" @click="exportAllArtifacts(props.id)">导出全部 (.zip)</button>
```

- [ ] **Step 3: Note.vue / Mindmap.vue 加「下载 .md/.mmd」按钮**

Note.vue 工具栏加：
```vue
<button class="btn btn-sm" @click="downloadArtifact(id, 'organize_markdown_file')">下载 .md</button>
```

Mindmap.vue 工具栏加：
```vue
<button class="btn btn-sm" @click="downloadArtifact(id, 'mindmap_mindmap_file')">下载 .mmd</button>
```

- [ ] **Step 4: 构建验证**

Run: `cd /Users/gejiawei/Desktop/ai_code/vid2note/desktop && npx vite build 2>&1 | tail -3`
Expected: 构建成功。

- [ ] **Step 5: Commit**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
git add desktop/src/renderer/api/task.js desktop/src/renderer/views/
git commit -m "feat(desktop): 任务详情/笔记/思维导图页加下载/导出按钮"
```

---

## Task 5: 端到端验证下载

- [ ] **Step 1: 启动后端跑任务，验证三个端点**

```bash
cd /Users/gejiawei/Desktop/ai_code/vid2note
set -a && source .env && set +a
.venv/bin/python -m uvicorn vid2note_server.main:app --port 8765 &
sleep 4
# 提交任务并等待完成...
TASK=task_xxx
curl -s http://127.0.0.1:8765/api/v1/tasks/$TASK/artifacts | python3.11 -m json.tool
curl -s -o /tmp/test.md http://127.0.0.1:8765/api/v1/tasks/$TASK/artifacts/organize_markdown_file
curl -s -o /tmp/test.zip http://127.0.0.1:8765/api/v1/tasks/$TASK/export
```

确认返回的文件内容正确、Content-Type 正确、zip 可解压。

- [ ] **Step 2: 前端验证**

重建 app，打开任务详情，点「导出全部」确认下载 zip，点笔记页「下载 .md」确认下载文件。

---

## Self-Review

**1. Spec coverage:** 列产物（Task 1）、单文件下载（Task 2）、zip 导出（Task 3）、前端按钮（Task 4）、E2E（Task 5）。覆盖 review 指出的「无 FileResponse 端点」Critical 缺口。

**2. Placeholder:** Step 1 的 baseURL 获取在 Task 4 有替代方案说明（`getBackendUrl()` IPC）。

**3. Type consistency:** `_ARTIFACT_META` 的键名 `transcribe_srt_file`/`organize_markdown_file`/`mindmap_mindmap_file` 与 `ArtifactStore.artifact_path` 的 `f"{node}_{name}"` 命名一致（node=transcribe/organize/mindmap，name=srt_file/markdown_file/mindmap_file），与 Phase 1 review 确认的实际产物文件名一致。
