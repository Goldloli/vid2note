<template>
  <div class="page">
    <div class="spread reveal" style="margin-bottom:20px; gap:16px; flex-wrap:wrap">
      <div class="row gap-m">
        <span class="plat-ico" :class="platClass" style="width:42px;height:42px;font-size:15px">{{ platChar }}</span>
        <div>
          <div class="row gap-s"><h1 style="font-size:20px">{{ title }}</h1><span class="badge" :class="badgeClass"><span class="d"></span>{{ statusLabel }}</span></div>
          <div class="muted mono-sm" style="margin-top:4px">{{ id }} · {{ task?.video_url || task?.video_file || '—' }}</div>
        </div>
      </div>
      <div class="row gap-s"><span class="tag">asrtools-b</span><span class="tag">qwen-turbo</span></div>
    </div>
    <div class="td-grid">
      <div>
        <div class="card card-pad reveal" style="margin-bottom:20px">
          <div class="section-title" style="margin-bottom:18px"><h2>处理流水线</h2><span class="mono-sm muted">6 节点 · DAG 串行</span></div>
          <div class="pipeline-flow">
            <div class="pf-line"><i :style="{height: lineFillPct + '%'}"></i></div>
            <div v-for="(node, i) in NODES" :key="node.key" class="pf-node" :class="nodeClass(i)">
              <div class="pf-ico"><span v-html="node.icon"></span></div>
              <div class="pf-body"><div class="top"><span class="pf-name">{{ node.name }} {{ node.key }}</span><span class="tag" :class="{muted: nodeState(i) !== 'done'}">{{ nodeHint(i) }}</span></div><div class="pf-desc">{{ node.desc }}</div></div>
              <div class="pf-right"><span class="mono-sm" :class="nodeState(i) === 'active' ? '' : 'muted'" :style="nodeState(i) === 'active' ? 'color:var(--accent)' : ''">{{ nodeTime(i) }}</span><span class="badge" :class="nodeBadge(i)" style="font-size:10px"><span class="d"></span>{{ nodeStateLabel(i) }}</span><button v-if="canRerun(i)" class="btn btn-sm" style="margin-top:4px" @click="rerunFrom(node.key)">重跑</button></div>
            </div>
          </div>
        </div>
        <div class="card reveal" style="overflow:hidden">
          <div class="toolbar" style="border-bottom:1px solid var(--border); padding:6px 10px">
            <div class="tabs" style="border:0; margin:0">
              <button class="tab" :class="{active: tab === 'srt'}" @click="tab = 'srt'">转录稿</button>
              <button class="tab" :class="{active: tab === 'note'}" @click="tab = 'note'">笔记预览</button>
              <button class="tab" :class="{active: tab === 'mindmap'}" @click="tab = 'mindmap'">思维导图</button>
              <button class="tab" :class="{active: tab === 'meta'}" @click="tab = 'meta'">元数据</button>
            </div>
            <button class="btn btn-sm" @click="onExportAll" title="导出全部产物（zip）">导出全部</button>
          </div>
          <div v-show="tab === 'srt'" style="padding:16px 18px"><pre v-if="artifacts?.srt" class="srt-pre">{{ artifacts.srt }}</pre><div v-else class="muted">暂无转录稿</div></div>
          <div v-show="tab === 'note'" style="padding:18px"><pre v-if="artifacts?.markdown" class="srt-pre note-pre">{{ artifacts.markdown }}</pre><div v-else class="muted">暂无笔记</div></div>
          <div v-show="tab === 'mindmap'" style="padding:18px"><pre v-if="artifacts?.mindmap" class="srt-pre">{{ artifacts.mindmap }}</pre><div v-else class="muted">暂无思维导图</div></div>
          <div v-show="tab === 'meta'" style="padding:18px"><dl class="kv" v-if="task"><dt>任务 ID</dt><dd>{{ task.id }}</dd><dt>来源</dt><dd>{{ task.video_url || task.video_file || '—' }}</dd><dt>状态</dt><dd>{{ task.status }}</dd><dt>ASR</dt><dd>{{ task.asr_provider || 'asrtools-b' }}</dd><dt>LLM</dt><dd>{{ task.llm_provider || 'qwen' }}</dd></dl></div>
        </div>
      </div>
      <div class="td-side">
        <div class="card card-pad reveal">
          <div class="row gap-m" style="margin-bottom:16px">
            <div class="ring"><svg width="96" height="96"><circle cx="48" cy="48" r="42" fill="none" stroke="var(--surface-3)" stroke-width="7"/><circle cx="48" cy="48" r="42" fill="none" stroke="var(--accent)" stroke-width="7" stroke-linecap="round" :stroke-dasharray="RING_LEN" :stroke-dashoffset="ringOffset"/></svg><div class="rv"><span>{{ progress }}%</span></div></div>
            <div class="col gap-xs"><span class="kicker">当前步骤</span><strong style="font-size:14px">{{ currentNodeLabel }}</strong><span class="mono-sm muted">{{ statusLabel }}</span></div>
          </div>
          <div class="progress striped" style="margin-bottom:14px"><i :style="{width: progress + '%'}"></i></div>
        </div>
        <div class="card reveal" style="overflow:hidden">
          <div class="toolbar"><strong style="font-size:12.5px">实时日志</strong><span class="mono-sm muted" style="margin-left:auto">SSE</span><span class="dot-live"></span></div>
          <div class="log-term">
            <div v-for="(line, i) in logs" :key="i" class="lt-line"><span class="lt-time">{{ line.time }}</span><span :class="logClass(line.level)">[{{ line.level }}]</span> {{ line.text }}</div>
            <div v-if="!logs.length" class="lt-line muted">等待事件…</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getTask, rerunTask, exportAllArtifacts } from '../api/task'
import { getProcessResult } from '../api/process'
import { TaskEventSource } from '../api/sse'

const props = defineProps({ id: { type: String, required: true } })

const RING_LEN = 263.9
const TH = [25, 45, 70, 95, 98, 100]
const NODES = [
  { key: 'download', name: '下载', desc: '通过下载器拉取视频流', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>' },
  { key: 'extract_audio', name: '提取音频', desc: 'ffmpeg 分离音轨，转 16bit PCM', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 14v-2a9 9 0 0118 0v2"/><rect x="2" y="14" width="5" height="7" rx="1.5"/><rect x="17" y="14" width="5" height="7" rx="1.5"/></svg>' },
  { key: 'transcribe', name: '转录', desc: 'ASR 语音识别 → SRT', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 11h4M7 15h7M15 11h2"/></svg>' },
  { key: 'organize', name: '整理笔记', desc: 'LLM 重组为结构化 Markdown', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>' },
  { key: 'mindmap', name: '思维导图', desc: '从笔记抽取层级 → Mermaid', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v3M12 10l-5 7M12 10l5 7"/></svg>' },
  { key: 'cleanup', name: '清理', desc: '按保留策略清理中间产物', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 6h18M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>' },
]

const task = ref(null)
const artifacts = ref(null)
const tab = ref('srt')
const logs = ref([])
let es = null

const progress = computed(() => task.value?.progress || 0)
const title = computed(() => {
  const src = task.value?.video_url || task.value?.video_file || ''
  return src.replace(/^https?:\/\//, '').split('/')[0] || props.id
})
const ringOffset = computed(() => RING_LEN * (1 - progress.value / 100))
const currentIndex = computed(() => {
  for (let i = 0; i < TH.length; i++) if (progress.value < TH[i]) return i
  return TH.length - 1
})
const lineFillPct = computed(() => {
  let p = Math.min(100, (currentIndex.value / (NODES.length - 1)) * 100)
  if (progress.value >= 100) p = 100
  return p
})
const currentNodeLabel = computed(() => NODES[currentIndex.value]?.name || '—')
const statusLabel = computed(() => ({ pending: '等待中', running: '处理中', completed: '已完成', failed: '失败', partial: '部分完成' }[task.value?.status] || task.value?.status || '—'))
const badgeClass = computed(() => ({ pending: 'pending', running: 'running', completed: 'completed', failed: 'failed', partial: 'warn' }[task.value?.status] || 'pending'))

const nodeState = (i) => {
  if (progress.value >= TH[i]) return 'done'
  if (i === currentIndex.value && task.value?.status !== 'completed') return 'active'
  if (task.value?.status === 'failed' && i === currentIndex.value) return 'failed'
  return 'idle'
}
const nodeClass = (i) => nodeState(i)
const nodeHint = (i) => nodeState(i) === 'done' ? NODES[i].key + ' ✓' : NODES[i].key + ' · 待处理'
const nodeTime = (i) => { const s = nodeState(i); return s === 'done' ? '完成' : s === 'active' ? '进行中' : '—' }
const nodeStateLabel = (i) => ({ done: '完成', active: '运行中', failed: '失败', idle: '等待' }[nodeState(i)] || '等待')
const nodeBadge = (i) => ({ done: 'completed', active: 'running', failed: 'failed', idle: 'pending' }[nodeState(i)] || 'pending')
const canRerun = (i) => nodeState(i) === 'failed' || task.value?.status === 'completed' || task.value?.status === 'partial'

const platClass = computed(() => {
  const s = task.value?.video_url || ''
  if (s.includes('bilibili') || s.includes('b23.tv')) return 'plat-bili'
  if (s.includes('youtube') || s.includes('youtu.be')) return 'plat-yt'
  return 'plat-file'
})
const platChar = computed(() => { const c = platClass.value; return c === 'plat-yt' ? '▶' : c === 'plat-bili' ? 'B' : '▲' })
const logClass = (level) => ({ info: 'lt-info', ok: 'lt-ok', warn: 'lt-warn', err: 'lt-err', dim: 'lt-dim' }[level] || 'lt-dim')

function _applyEvent(event) {
  if (!event) return
  if (event.node_name && event.node_status) {
    logs.value.push({ time: (event.timestamp || '').slice(11, 19), level: event.node_status === 'failed' ? 'err' : event.event_type.includes('completed') ? 'ok' : 'info', text: `${event.node_name}: ${event.message || event.node_status}` })
  }
  if (event.progress !== undefined && task.value) task.value = { ...task.value, progress: event.progress }
  if (event.event_type === 'task.completed' && task.value) { task.value = { ...task.value, status: 'completed', progress: 100 }; _loadResult() }
  if (event.event_type === 'task.failed' && task.value) task.value = { ...task.value, status: 'failed' }
}
async function rerunFrom(nodeKey) { try { await rerunTask(props.id, nodeKey); logs.value = []; _subscribe() } catch (e) {} }
async function onExportAll() { try { await exportAllArtifacts(props.id) } catch (e) {} }
async function _loadResult() {
  try {
    const res = await getProcessResult(props.id)
    // 后端返回 {task_id,status,progress,artifacts:{...}}，模板只读 artifacts 内层
    artifacts.value = res.artifacts || res || {}
  } catch (e) {}
}
function _subscribe() { if (es) es.close(); es = new TaskEventSource(props.id, _applyEvent, () => {}); es.connect() }
onMounted(async () => { try { task.value = await getTask(props.id); _loadResult(); _subscribe() } catch (e) {} })
onUnmounted(() => { if (es) es.close() })
</script>

<style scoped>
.td-grid { display:grid; grid-template-columns: 1fr 340px; gap:20px; align-items:start; }
.td-side { position:sticky; top:18px; display:flex; flex-direction:column; gap:16px; }
.ring { position:relative; width:96px; height:96px; }
.ring svg { transform: rotate(-90deg); }
.ring .rv { position:absolute; inset:0; display:grid; place-items:center; font-family:var(--font-display); font-size:24px; font-weight:600; color:var(--fg-strong); }
.kv { display:grid; grid-template-columns: 92px 1fr; gap:6px 12px; font-size:12.5px; }
.kv dt { color:var(--muted-2); }
.kv dd { color:var(--fg); font-family:var(--font-mono); }
.srt-pre { white-space:pre-wrap; word-break:break-word; font-family:var(--font-mono); font-size:12.5px; background:var(--surface-3); padding:14px; border-radius:var(--radius-sm); max-height:420px; overflow:auto; }
.note-pre { font-family:var(--font-body); font-size:13.5px; line-height:1.7; }
@media (max-width: 900px) { .td-grid { grid-template-columns: 1fr; } }
</style>
