<template>
  <div class="page">
    <div class="spread" style="margin-bottom:18px">
      <div><strong style="font-size:16px">{{ task?.title || task?.source_url || id }}</strong> &nbsp;<span v-if="task" class="badge" :class="task.status"><span class="d"></span>{{ statusText(task.status) }}</span></div>
      <div class="row gap-s">
        <button v-if="task&&(task.status==='failed'||task.status==='completed')" class="btn btn-sm" @click="rerun">{{ $t('task.rerun') }}</button>
        <button v-if="task&&(task.status==='running'||task.status==='pending')" class="btn btn-sm" @click="cancel">{{ $t('task.cancel') }}</button>
      </div>
    </div>
    <section class="card card-pad" style="margin-bottom:18px">
      <div class="row" style="align-items:center;gap:20px">
        <div class="progress-ring">
          <svg viewBox="0 0 80 80"><circle cx="40" cy="40" r="34" class="bg"/><circle cx="40" cy="40" r="34" class="fg" :stroke-dasharray="ring.dash" :stroke-dashoffset="ring.off"/></svg>
          <div class="ring-num">{{ task?.progress || 0 }}%</div>
        </div>
        <div style="flex:1;min-width:0">
          <PipelineRail :nodes="nodeStatuses" />
          <div class="node-list">
            <div v-for="n in nodeDetail" :key="n.key" class="node-row">
              <span class="badge" :class="n.status"><span class="d"></span>{{ $t(n.label) }}</span>
              <span class="mono-sm muted" style="width:56px">{{ n.duration }}</span>
              <span class="mono-sm muted" v-if="n.product" style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ n.product }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section class="card" style="margin-bottom:18px">
      <div class="toolbar">
        <button v-for="t in tabs" :key="t.v" class="chip btn-sm" :class="{active: tab===t.v}" @click="switchTab(t.v)">{{ $t(t.l) }}</button>
      </div>
      <div class="tab-body">
        <pre v-if="tab==='srt'" class="tab-pre">{{ srtText || '…' }}</pre>
        <div v-else-if="tab==='note'" class="note-md" v-html="noteHtml"></div>
        <table v-else class="kv">
          <tr v-for="r in metaRows" :key="r.k"><td class="muted mono-sm">{{ $t(r.k) }}</td><td>{{ r.v }}</td></tr>
        </table>
      </div>
    </section>
    <section class="card">
      <div class="toolbar"><span class="kicker">{{ $t('task.liveLog') }}</span></div>
      <div class="log-term"><div v-for="(l,i) in logs" :key="i" :class="logClass(l)"><span class="lt-time">{{ l.ts }}</span> {{ l.text }}</div></div>
    </section>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import { getTask, streamTask, rerunTask, cancelTask, getProductUrl } from '@/api'
import { i18n } from '@/i18n'
import PipelineRail from '@/components/PipelineRail.vue'
const route = useRoute(); const id = route.params.id
const task = ref({}); const logs = ref([]); const tab = ref('srt')
const srtText = ref(''); const noteHtml = ref('')
// [node key, 中文标签, 对应产物 kind] —— 节点名为流水线技术术语,保留中文
const NODES = [['download','pipeline.download','video'],['extract_audio','pipeline.audio','audio'],['asr','pipeline.asr','srt'],['note','pipeline.note','note'],['mindmap','pipeline.mindmap','mindmap'],['cleanup','pipeline.cleanup','']]
const tabs = [{v:'srt',l:'task.tabTranscript'},{v:'note',l:'task.tabNote'},{v:'meta',l:'task.tabMeta'}]
const nodeStatuses = computed(() => task.value?.node_statuses || {})
const statusText = s => i18n.global.t('status.' + s)
const logClass = l => ({ info: 'lt-info', ok: 'lt-ok', warn: 'lt-warn', err: 'lt-err', dim: 'lt-dim' }[l.level] || 'lt-info')
const ring = computed(() => { const p = (task.value?.progress || 0) / 100; const c = 2 * Math.PI * 34; return { dash: c, off: c * (1 - p) } })
function productOf(kind) {
  const t = task.value || {}
  if (kind === 'video') return t.video_path
  if (kind === 'audio') return t.audio_path
  if (kind === 'srt') return t.srt_path
  if (kind === 'note') return t.note_path
  if (kind === 'mindmap') return (t.mindmap_paths || []).join(', ')
  return ''
}
const nodeDetail = computed(() => NODES.map(([k, label, kind]) => {
  const ns = (task.value?.node_statuses || {})[k] || {}
  const dur = ns.started_at && ns.finished_at ? durBetween(ns.started_at, ns.finished_at) : (ns.status === 'running' ? i18n.global.t('task.inProgress') : '—')
  const prod = ns.status === 'completed' && kind ? baseName(productOf(kind)) : ''
  return { key: k, label, status: ns.status || 'pending', duration: dur, product: prod }
}))
const metaRows = computed(() => {
  const t = task.value || {}
  return [
    {k:'task.metaId', v:t.id}, {k:'task.metaSource', v:t.source_url || t.source_type}, {k:'task.metaAsr', v: i18n.global.t('engine.short.' + (t.asr_engine || 'asrtools'))},
    {k:'task.metaLlm', v:`${t.llm_provider || ''}/${t.llm_model || ''}`}, {k:'task.metaLang', v:t.output_language},
    {k:'task.metaShot', v:t.extract_images ? i18n.global.t('task.shotOn') : i18n.global.t('task.shotOff')}, {k:'task.metaCreated', v:fmt(t.created_at)}, {k:'task.metaFinished', v:fmt(t.finished_at)},
    {k:'task.metaError', v:t.error || ''},
  ].filter(r => r.v)
})
function durBetween(a, b) { try { return Math.round((new Date(b) - new Date(a)) / 1000) + 's' } catch (e) { return '—' } }
function baseName(p) { return p ? String(p).split('/').pop() : '' }
function fmt(d) { return d ? String(d).replace('T', ' ').slice(0, 19) : '—' }
let es, timer
async function load() { try { task.value = await getTask(id) } catch (e) {} }
async function loadTab() {
  if (tab.value === 'srt') { try { const r = await fetch(getProductUrl(id, 'srt')); srtText.value = r.ok ? await r.text() : i18n.global.t('task.transcriptEmpty') } catch (e) { srtText.value = i18n.global.t('task.loadFail') } }
  else if (tab.value === 'note') { try { const r = await fetch(getProductUrl(id, 'note')); noteHtml.value = r.ok ? marked.parse(await r.text()) : '<p>' + i18n.global.t('task.noteEmpty') + '</p>' } catch (e) {} }
}
function switchTab(v) { tab.value = v; loadTab() }
function openStream() {
  es && es.close()
  es = streamTask(id)
  es.addEventListener('snapshot', e => { const d = JSON.parse(e.data); if (d.payload) task.value = { ...task.value, ...d.payload } })
  es.addEventListener('node-entered', e => { const d = JSON.parse(e.data); const n = d.payload?.node; if (n) task.value.node_statuses = { ...(task.value.node_statuses || {}), [n]: { status: 'running', started_at: new Date().toISOString() } } })
  es.addEventListener('node-completed', e => { const d = JSON.parse(e.data); const n = d.payload?.node; if (n) { const cur = (task.value.node_statuses || {})[n] || {}; task.value.node_statuses = { ...(task.value.node_statuses || {}), [n]: { ...cur, status: 'completed', finished_at: new Date().toISOString() } } } })
  es.addEventListener('node-failed', e => { const d = JSON.parse(e.data); const n = d.payload?.node; if (n) task.value.node_statuses = { ...(task.value.node_statuses || {}), [n]: { status: 'failed' } } })
  es.addEventListener('log', e => { const d = JSON.parse(e.data); logs.value.push({ ts: new Date(d.ts * 1000).toLocaleTimeString(), text: d.payload?.message || d.payload?.msg || '', level: d.payload?.level || 'info' }) })
  es.addEventListener('task-completed', () => { task.value.status = 'completed'; task.value.progress = 100; es.close() })
  es.addEventListener('task-failed', e => { const d = JSON.parse(e.data); task.value.status = 'failed'; logs.value.push({ ts: '--', text: i18n.global.t('task.failed') + (d.payload?.error || ''), level: 'err' }); es.close() })
}
async function rerun() { await rerunTask(id); await load(); openStream() }
async function cancel() { await cancelTask(id); await load() }
onMounted(async () => { await load(); await loadTab(); openStream(); timer = setInterval(load, 3000) })
onUnmounted(() => { es && es.close(); clearInterval(timer) })
</script>
<style scoped>
.progress-ring { width: 80px; height: 80px; position: relative; flex: none; }
.progress-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
.progress-ring circle { fill: none; stroke-width: 8; }
.progress-ring circle.bg { stroke: var(--border); }
.progress-ring circle.fg { stroke: var(--accent); stroke-linecap: round; transition: stroke-dashoffset .3s; }
.ring-num { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; }
.node-list { margin-top: 14px; display: flex; flex-direction: column; gap: 6px; }
.node-row { display: flex; gap: 12px; align-items: center; }
.tab-body { padding: 14px; max-height: 360px; overflow: auto; }
.tab-pre { white-space: pre-wrap; word-break: break-word; font-family: var(--mono); font-size: 12px; margin: 0; }
.kv td { padding: 4px 12px 4px 0; }
.kv td:first-child { width: 100px; }
</style>
