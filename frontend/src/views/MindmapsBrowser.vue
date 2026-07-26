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
      <div class="card mm-viewport" style="height:100%">
        <div class="mm-scaler" :style="{transform:`scale(${scale})`}"><svg ref="svgRef" class="markmap"></svg></div>
        <div v-if="!ready" class="muted mono-sm" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center">{{ errMsg || $t('mindmap.rendering') }}</div>
      </div>
    </main>
    <aside class="br-right card">
      <div class="br-tabs">
        <button class="chip btn-sm" :class="{active:tab==='outline'}" @click="tab='outline'">{{ $t('mindmap.outlineTitle') }}</button>
        <button class="chip btn-sm" :class="{active:tab==='action'}" @click="tab='action'">{{ $t('browser.action') }}</button>
      </div>
      <div v-if="tab==='outline'" class="br-tab-body">
        <pre class="outline-pre">{{ outline || '…' }}</pre>
      </div>
      <div v-else class="br-tab-body">
        <div class="row gap-s" style="margin-bottom:8px">
          <button class="btn btn-sm" @click="zoomBy(0.2)">{{ $t('mindmap.zoomIn') }}</button>
          <button class="btn btn-sm" @click="zoomBy(-0.2)">{{ $t('mindmap.zoomOut') }}</button>
          <button class="btn btn-sm" @click="fit">{{ $t('mindmap.fit') }}</button>
        </div>
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
const svgRef = ref(null); const ready = ref(false); const errMsg = ref(''); const scale = ref(1); const outline = ref(''); const tab = ref('outline')
let mm = null
const formats = computed(() => task.value?.mindmap_formats || [])
const exportEntries = computed(() => formats.value.map((fmt, i) => ({ fmt, i })))
function exportLabel(fmt) { return { xmind: 'mindmap.exportXmind', png: 'mindmap.exportPng', md: 'mindmap.exportMd' }[fmt] || fmt }
function mmUrl(i) { return selectedId.value ? `${getProductUrl(selectedId.value, 'mindmap')}?index=${i}` : '' }
const fmt = d => d ? String(d).replace('T', ' ').slice(0, 10) : ''
let dt
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
    mm = Markmap.create(svgRef.value, { initialExpandLevel: 2, zoom: false, duration: 300, padding: 16 }, root)
    ready.value = true
  } catch (e) { errMsg.value = i18n.global.t('mindmap.renderFail') + e.message }
}
async function loadOutline(id) {
  const mdIdx = (task.value?.mindmap_formats || []).indexOf('md')
  if (mdIdx >= 0) { try { const res = await fetch(mmUrl(mdIdx)); if (res.ok) { outline.value = await res.text(); return } } catch (e) {} }
  try { outline.value = outlineFromNote(await fetchNote(id)) } catch (e) { outline.value = '' }
}
function outlineFromNote(md) { const out = []; for (const ln of md.split('\n')) { const m = ln.match(/^(#{1,4})\s+(.*)$/); if (m) { out.push('  '.repeat(m[1].length - 1) + '- ' + m[2].trim()) } } return out.join('\n') }
function zoomBy(d) { scale.value = Math.min(2, Math.max(0.4, +(scale.value + d).toFixed(2))) }
function fit() { scale.value = 1; mm && mm.fit() }
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
.br-mid { flex: 1; min-width: 0; }
.mm-viewport { position: relative; overflow: hidden; }
.mm-scaler { width: 100%; height: 100%; transform-origin: center center; transition: transform .2s; }
.markmap { width: 100%; height: 100%; display: block; }
.br-right { width: 280px; flex: none; display: flex; flex-direction: column; }
.br-tabs { display: flex; gap: 6px; margin-bottom: 10px; }
.br-tab-body { flex: 1; overflow: auto; }
.outline-pre { white-space: pre-wrap; word-break: break-word; font-family: var(--mono); font-size: 12px; color: var(--text-2); margin: 0; line-height: 1.7; }
.block { display: block; margin-bottom: 6px; }
</style>
