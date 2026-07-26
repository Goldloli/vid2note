<template>
  <div class="page">
    <div class="spread" style="margin-bottom:14px">
      <strong>{{ $t('mindmap.title') }}</strong>
      <div class="row gap-s">
        <button class="btn btn-sm" @click="zoomBy(0.2)">{{ $t('mindmap.zoomIn') }}</button>
        <button class="btn btn-sm" @click="zoomBy(-0.2)">{{ $t('mindmap.zoomOut') }}</button>
        <button class="btn btn-sm" @click="fit">{{ $t('mindmap.fit') }}</button>
        <button class="btn btn-sm" @click="center">{{ $t('mindmap.center') }}</button>
        <span class="muted mono-sm">{{ Math.round(scale * 100) }}%</span>
        <span style="width:12px"></span>
        <button class="chip btn-sm" :class="{active: view==='split'}" @click="view='split'">{{ $t('mindmap.split') }}</button>
        <button class="chip btn-sm" :class="{active: view==='map'}" @click="view='map'">{{ $t('mindmap.mapOnly') }}</button>
        <button class="chip btn-sm" :class="{active: view==='text'}" @click="view='text'">{{ $t('mindmap.outlineOnly') }}</button>
      </div>
    </div>
    <div :class="['mm-layout', view]">
      <div v-if="view !== 'text'" class="card mm-viewport">
        <div class="mm-scaler" :style="{ transform: `scale(${scale})` }"><svg ref="svgRef" class="markmap"></svg></div>
        <div v-if="!ready" class="muted mono-sm" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center">{{ errMsg || $t('mindmap.rendering') }}</div>
      </div>
      <aside v-if="view !== 'map'" class="card mm-outline">
        <div class="kicker" style="margin-bottom:10px">{{ $t('mindmap.outlineTitle') }}</div>
        <pre class="outline-pre">{{ outline || '…' }}</pre>
      </aside>
    </div>
    <div class="card" style="margin-top:14px">
      <div class="kicker" style="margin-bottom:10px">{{ $t('mindmap.exportTitle') }}</div>
      <div class="row gap-s">
        <a v-for="f in exportEntries" :key="f.fmt" class="btn btn-sm" :href="getProductUrl(id,'mindmap') + `?index=${f.i}`" :download="`mindmap.${f.fmt}`">{{ $t(exportLabel(f.fmt)) }}</a>
        <span v-if="!exportEntries.length" class="muted mono-sm">{{ $t('mindmap.noMap') }}</span>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { getProductUrl, getTask } from '@/api'
import { i18n } from '@/i18n'
const id = useRoute().params.id
const svgRef = ref(null); const ready = ref(false); const errMsg = ref(''); const scale = ref(1); const outline = ref(''); const task = ref({}); const view = ref('split')
let mm = null
const formats = computed(() => task.value?.mindmap_formats || [])
const exportEntries = computed(() => formats.value.map((fmt, i) => ({ fmt, i })))
function exportLabel(fmt) { return { xmind: 'mindmap.exportXmind', png: 'mindmap.exportPng', md: 'mindmap.exportMd' }[fmt] || fmt }
async function loadTask() { try { task.value = await getTask(id) } catch (e) {} }
async function loadNote() { const res = await fetch(getProductUrl(id, 'note')); if (!res.ok) throw new Error(i18n.global.t('mindmap.noteNotReady')); return await res.text() }
async function loadOutline() {
  const mdIdx = formats.value.indexOf('md')
  if (mdIdx >= 0) { try { const res = await fetch(getProductUrl(id, 'mindmap') + `?index=${mdIdx}`); if (res.ok) { outline.value = await res.text(); return } } catch (e) {} }
  try { outline.value = outlineFromNote(await loadNote()) } catch (e) { outline.value = '' }
}
function outlineFromNote(md) { const out = []; for (const ln of md.split('\n')) { const m = ln.match(/^(#{1,4})\s+(.*)$/); if (m) { const d = m[1].length; out.push('  '.repeat(d - 1) + '- ' + m[2].trim()) } } return out.join('\n') }
async function renderMap() {
  try {
    const md = await loadNote()
    const [{ Transformer }, { Markmap }] = await Promise.all([import('markmap-lib'), import('markmap-view')])
    const { root } = new Transformer().transform(md)
    mm = Markmap.create(svgRef.value, { initialExpandLevel: 2, zoom: false, duration: 300, padding: 16 }, root)
    ready.value = true
  } catch (e) { errMsg.value = i18n.global.t('mindmap.renderFail') + e.message }
}
function zoomBy(delta) { scale.value = Math.min(2, Math.max(0.4, +(scale.value + delta).toFixed(2))) }
function fit() { scale.value = 1; mm && mm.fit() }
function center() { scale.value = 1; mm && mm.rescale() }
onMounted(async () => { await loadTask(); await Promise.all([renderMap(), loadOutline()]) })
onBeforeUnmount(() => mm && mm.destroy())
</script>
<style scoped>
.mm-layout { display: flex; gap: 14px; align-items: stretch; }
.mm-layout.map .mm-viewport { flex: 1; } .mm-layout.text .mm-outline { flex: 1; width: auto; }
.mm-viewport { flex: 1; min-width: 0; height: calc(100vh - 250px); overflow: hidden; position: relative; }
.mm-scaler { width: 100%; height: 100%; transform-origin: center center; transition: transform .2s; }
.markmap { width: 100%; height: 100%; display: block; }
.mm-outline { width: 300px; flex: none; overflow: auto; max-height: calc(100vh - 250px); padding: 14px; }
.outline-pre { white-space: pre-wrap; word-break: break-word; font-family: var(--mono); font-size: 12px; color: var(--text-2); margin: 0; line-height: 1.7; }
</style>
