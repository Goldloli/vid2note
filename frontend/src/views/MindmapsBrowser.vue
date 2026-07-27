<template>
  <div class="browser">
    <aside class="br-left card">
      <input class="input" v-model="q" :placeholder="$t('history.searchPh')" @input="debounced" style="margin-bottom:8px">
      <div class="br-list">
        <a v-for="t in items" :key="t.id" :class="['br-item',{active:selectedId===t.id}]" @click="select(t.id)">
          <div class="br-item-title">{{ displayName(t) }}</div>
        </a>
        <div v-if="!items.length" class="muted mono-sm" style="padding:16px;text-align:center">{{ $t('console.noCompleted') }}</div>
      </div>
    </aside>
    <main class="br-mid">
      <div class="mm-toolbar row gap-s">
        <button class="btn btn-sm" @click="zoomBy(0.2)">{{ $t('mindmap.zoomIn') }}</button>
        <button class="btn btn-sm" @click="zoomBy(-0.2)">{{ $t('mindmap.zoomOut') }}</button>
        <button class="btn btn-sm" @click="pan(0,-60)">↑</button>
        <button class="btn btn-sm" @click="pan(0,60)">↓</button>
        <button class="btn btn-sm" @click="pan(-60,0)">←</button>
        <button class="btn btn-sm" @click="pan(60,0)">→</button>
        <button class="btn btn-sm" @click="fit">{{ $t('mindmap.fit') }}</button>
        <span class="muted mono-sm">{{ Math.round(scale * 100) }}%</span>
      </div>
      <div class="card mm-viewport" @mousedown.middle.prevent="startPan" @wheel.prevent="onWheel">
        <div class="mm-scaler" :style="{ transform: `translate(${tx}px, ${ty}px) scale(${scale})` }"><svg ref="svgRef" class="markmap"></svg></div>
        <div v-if="!ready" class="muted mono-sm" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center">{{ errMsg || $t('mindmap.rendering') }}</div>
      </div>
    </main>
    <aside class="br-right card">
      <div class="br-tabs">
        <button class="chip btn-sm" :class="{active:tab==='outline'}" @click="tab='outline'">{{ $t('mindmap.outlineTitle') }}</button>
        <button class="chip btn-sm" :class="{active:tab==='action'}" @click="tab='action'">{{ $t('browser.action') }}</button>
      </div>
      <div v-if="tab==='outline'" class="br-tab-body"><pre class="outline-pre">{{ outline || '…' }}</pre></div>
      <div v-else class="br-tab-body">
        <a v-for="f in exportEntries" :key="f.fmt" class="btn btn-sm block" :href="mmUrl(f.i)" :download="`mindmap.${f.fmt}`">{{ $t(exportLabel(f.fmt)) }}</a>
        <router-link class="btn btn-sm block" :to="`/notes?id=${selectedId}`">{{ $t('note.title') }}</router-link>
      </div>
    </aside>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { listTasks, getTask, getProductUrl } from '@/api'
import { i18n } from '@/i18n'
import { displayName } from '@/format'
const route = useRoute()
const items = ref([]); const q = ref(''); const selectedId = ref(''); const task = ref(null)
const svgRef = ref(null); const ready = ref(false); const errMsg = ref('')
const scale = ref(1); const tx = ref(0); const ty = ref(0)
const outline = ref(''); const tab = ref('outline')
let mm = null; let dt
const formats = computed(() => task.value?.mindmap_formats || [])
const exportEntries = computed(() => formats.value.map((fmt, i) => ({ fmt, i })))
function exportLabel(fmt) { return { xmind: 'mindmap.exportXmind', png: 'mindmap.exportPng', md: 'mindmap.exportMd' }[fmt] || fmt }
function mmUrl(i) { return selectedId.value ? `${getProductUrl(selectedId.value, 'mindmap')}?index=${i}` : '' }
async function reload() {
  try {
    const r = await listTasks({ status: 'completed', q: q.value || undefined, page: 1, page_size: 100 })
    items.value = r.items || []
    if (!selectedId.value && items.value.length) select(items.value[0].id)
  } catch (e) {}
}
function debounced() { clearTimeout(dt); dt = setTimeout(reload, 300) }
async function select(id) {
  selectedId.value = id; tab.value = 'outline'; ready.value = false; errMsg.value = ''
  scale.value = 1; tx.value = 0; ty.value = 0
  mm && mm.destroy(); mm = null
  try { task.value = await getTask(id) } catch (e) { task.value = null }
  await Promise.all([renderMap(id), loadOutline(id)])
}
async function fetchNote(id) { const res = await fetch(getProductUrl(id, 'note')); if (!res.ok) throw new Error(i18n.global.t('mindmap.noteNotReady')); return await res.text() }
async function renderMap(id) {
  try {
    const md = await fetchNote(id)
    const [{ Transformer }, { Markmap }] = await Promise.all([import('markmap-lib'), import('markmap-view')])
    const { root } = new Transformer().transform(md)
    mm = Markmap.create(svgRef.value, { initialExpandLevel: -1, zoom: false, duration: 300, padding: 16 }, root)
    ready.value = true
  } catch (e) { errMsg.value = i18n.global.t('mindmap.renderFail') + e.message }
}
async function loadOutline(id) {
  const mdIdx = (task.value?.mindmap_formats || []).indexOf('md')
  if (mdIdx >= 0) { try { const res = await fetch(mmUrl(mdIdx)); if (res.ok) { outline.value = await res.text(); return } } catch (e) {} }
  try { outline.value = outlineFromNote(await fetchNote(id)) } catch (e) { outline.value = '' }
}
function outlineFromNote(md) { const out = []; for (const ln of md.split('\n')) { const m = ln.match(/^(#{1,4})\s+(.*)$/); if (m) { out.push('  '.repeat(m[1].length - 1) + '- ' + m[2].trim()) } } return out.join('\n') }
function zoomBy(d) { scale.value = Math.min(3, Math.max(0.2, +(scale.value + d).toFixed(2))) }
function onWheel(e) { zoomBy(e.deltaY < 0 ? 0.1 : -0.1) }
function pan(dx, dy) { tx.value += dx; ty.value += dy }
function fit() { scale.value = 1; tx.value = 0; ty.value = 0; mm && mm.fit() }
// 鼠标中键按下拖动平移
function startPan(e) {
  let lx = e.clientX, ly = e.clientY
  const move = (ev) => { tx.value += ev.clientX - lx; ty.value += ev.clientY - ly; lx = ev.clientX; ly = ev.clientY }
  const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}
onMounted(() => { const id = route.query.id; reload().then(() => { if (id) select(String(id)) }) })
onBeforeUnmount(() => { mm && mm.destroy(); clearTimeout(dt) })
</script>
<style scoped>
.browser { display: flex; gap: 14px; height: calc(100vh - 90px); }
.br-left { width: 240px; flex: none; display: flex; flex-direction: column; }
.br-list { flex: 1; overflow: auto; }
.br-item { display: block; padding: 10px; border-radius: 6px; cursor: pointer; border-left: 2px solid transparent; }
.br-item:hover { background: var(--card-2); }
.br-item.active { background: var(--accent-soft); border-left-color: var(--accent); }
.br-item-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.br-mid { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.mm-toolbar { margin-bottom: 8px; }
.mm-viewport { flex: 1; position: relative; overflow: hidden; }
.mm-scaler { width: 100%; height: 100%; transform-origin: center center; transition: transform .2s; overflow: visible; }
.markmap { width: 100%; height: 100%; display: block; overflow: visible; }
.br-right { width: 280px; flex: none; display: flex; flex-direction: column; }
.br-tabs { display: flex; gap: 6px; margin-bottom: 10px; }
.br-tab-body { flex: 1; overflow: auto; }
.outline-pre { white-space: pre-wrap; word-break: break-word; font-family: var(--mono); font-size: 12px; color: var(--text-2); margin: 0; line-height: 1.7; }
.block { display: block; margin-bottom: 6px; }
</style>
