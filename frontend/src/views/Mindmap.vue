<template>
  <div class="page page-wide mindmap-detail">
    <PageHeader :title="task.title || $t('mindmap.title')" :subtitle="$t('mindmap.detailSubtitle')" icon="mindmap">
      <template #actions>
        <router-link class="btn" :to="`/note/${id}`"><AppIcon name="notes" :size="16" />{{ $t('note.title') }}</router-link>
        <button class="btn btn-primary" type="button" :disabled="!ready" @click="exportPng"><AppIcon name="download" :size="16" />{{ $t('mindmap.exportPng') }}</button>
      </template>
    </PageHeader>

    <div class="view-mode-bar surface">
      <span>{{ $t('mindmap.viewMode') }}</span>
      <div class="view-tabs" role="group" :aria-label="$t('mindmap.viewMode')">
        <button :class="{ active: view === 'split' }" type="button" @click="view = 'split'">{{ $t('mindmap.split') }}</button>
        <button :class="{ active: view === 'map' }" type="button" @click="view = 'map'">{{ $t('mindmap.mapOnly') }}</button>
        <button :class="{ active: view === 'text' }" type="button" @click="view = 'text'">{{ $t('mindmap.outlineOnly') }}</button>
      </div>
    </div>

    <div class="mindmap-shell" :class="{ 'map-only': view === 'map', 'text-only': view === 'text' }">
      <main v-if="view !== 'text'" class="map-surface surface">
        <div class="map-toolbar">
          <strong>{{ $t('mindmap.canvas') }}</strong>
          <div class="map-controls" role="toolbar" :aria-label="$t('mindmap.viewControls')">
            <button class="icon-btn" type="button" :title="$t('mindmap.zoomIn')" :aria-label="$t('mindmap.zoomIn')" @click="zoomBy(0.2)"><AppIcon name="zoom-in" :size="17" /></button>
            <button class="icon-btn" type="button" :title="$t('mindmap.zoomOut')" :aria-label="$t('mindmap.zoomOut')" @click="zoomBy(-0.2)"><AppIcon name="zoom-out" :size="17" /></button>
            <span class="zoom-value">{{ Math.round(scale * 100) }}%</span>
            <button class="btn btn-sm" type="button" @click="fit"><AppIcon name="arrows-out" :size="15" />{{ $t('mindmap.fit') }}</button>
            <button class="btn btn-sm" type="button" @click="center"><AppIcon name="center" :size="15" />{{ $t('mindmap.center') }}</button>
          </div>
        </div>
        <div class="map-viewport" @mousedown.middle.prevent="startPan" @wheel.prevent="onWheel">
          <div class="map-grid" aria-hidden="true"></div>
          <div class="mm-scaler" :style="{ transform: `translate(${tx}px, ${ty}px) scale(${scale})` }">
            <svg ref="svgRef" class="markmap"></svg>
          </div>
          <LoadingState v-if="loading && !errMsg" class="map-state" :label="$t('mindmap.rendering')" :rows="4" />
          <EmptyState
            v-else-if="errMsg"
            class="map-state"
            :title="$t('mindmap.renderErrorTitle')"
            :description="errMsg"
            icon="warning"
            tone="danger"
          >
            <template #actions>
              <button class="btn btn-sm" type="button" @click="reload"><AppIcon name="arrow-clockwise" :size="15" />{{ $t('browser.retry') }}</button>
            </template>
          </EmptyState>
        </div>
      </main>

      <aside v-if="view !== 'map'" class="outline-panel surface" :class="{ full: view === 'text' }">
        <div class="panel-head"><AppIcon name="book-open" :size="16" />{{ $t('mindmap.outlineTitle') }}</div>
        <pre v-if="outline" class="outline-pre">{{ outline }}</pre>
        <EmptyState v-else class="outline-empty" :title="$t('mindmap.noOutline')" :description="$t('mindmap.noOutlineHint')" icon="book-open" />
      </aside>
    </div>

    <section class="export-panel surface">
      <SectionHeader :title="$t('mindmap.exportTitle')" :description="$t('mindmap.exportHint')" />
      <div class="export-actions">
        <a
          v-for="entry in hrefEntries"
          :key="entry.fmt"
          class="btn"
          :href="`${getProductUrl(id, 'mindmap')}?index=${entry.i}`"
          :download="`mindmap.${entry.fmt}`"
        >
          <AppIcon name="download" :size="16" />
          {{ $t(exportLabel(entry.fmt)) }}
        </a>
        <button class="btn" type="button" :disabled="!ready" @click="exportPng"><AppIcon name="download" :size="16" />{{ $t('mindmap.exportPng') }}</button>
        <span v-if="!exportEntries.length" class="inline-note">{{ $t('mindmap.noMap') }}</span>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { getProductUrl, getTask } from '@/api'
import { i18n } from '@/i18n'

const id = useRoute().params.id
const svgRef = ref(null)
const ready = ref(false)
const errMsg = ref('')
const loading = ref(true)
const scale = ref(1)
const tx = ref(0)
const ty = ref(0)
const outline = ref('')
const task = ref({})
const view = ref('split')
let markmap

const formats = computed(() => task.value?.mindmap_formats || [])
const exportEntries = computed(() => formats.value.map((format, index) => ({ fmt: format, i: index })))
const hrefEntries = computed(() => exportEntries.value.filter(entry => entry.fmt !== 'png'))

function exportLabel(format) {
  return { xmind: 'mindmap.exportXmind', png: 'mindmap.exportPng', md: 'mindmap.exportMd' }[format] || format
}
async function loadTask() {
  try {
    task.value = await getTask(id)
  } catch {
    task.value = {}
  }
}
async function loadNote() {
  const response = await fetch(getProductUrl(id, 'note'))
  if (!response.ok) throw new Error(i18n.global.t('mindmap.noteNotReady'))
  return await response.text()
}
async function loadOutline() {
  try {
    outline.value = outlineFromNote(await loadNote())
  } catch {
    outline.value = ''
  }
}
function outlineFromNote(markdown) {
  const output = []
  for (const line of markdown.split('\n')) {
    const match = line.match(/^(#{1,4})\s+(.*)$/)
    if (match) output.push(`${'  '.repeat(match[1].length - 1)}- ${match[2].trim()}`)
  }
  return output.join('\n')
}
async function renderMap() {
  try {
    const markdown = await loadNote()
    const [{ Transformer }, { Markmap }] = await Promise.all([import('markmap-lib'), import('markmap-view')])
    const { root } = new Transformer().transform(markdown)
    markmap = Markmap.create(svgRef.value, { initialExpandLevel: -1, zoom: false, duration: 220, padding: 18 }, root)
    ready.value = true
  } catch (error) {
    errMsg.value = i18n.global.t('mindmap.renderFail') + error.message
  }
}
async function reload() {
  loading.value = true
  ready.value = false
  errMsg.value = ''
  if (markmap) markmap.destroy()
  markmap = null
  await nextTick()
  await Promise.all([loadTask(), renderMap(), loadOutline()])
  loading.value = false
}
function zoomBy(delta) {
  scale.value = Math.min(3, Math.max(0.2, +(scale.value + delta).toFixed(2)))
}
function onWheel(event) {
  const factor = Math.exp(-event.deltaY * 0.001)
  scale.value = Math.min(3, Math.max(0.2, +(scale.value * factor).toFixed(3)))
}
function fit() {
  scale.value = 1
  tx.value = 0
  ty.value = 0
  if (markmap) markmap.fit()
}
function center() {
  scale.value = 1
  tx.value = 0
  ty.value = 0
  if (markmap) markmap.rescale()
}
function exportPng() {
  const svg = svgRef.value
  if (!svg) return
  const viewBox = svg.viewBox.baseVal
  const width = (viewBox && viewBox.width) || svg.clientWidth || 1200
  const height = (viewBox && viewBox.height) || svg.clientHeight || 800
  const clone = svg.cloneNode(true)
  clone.setAttribute('width', width)
  clone.setAttribute('height', height)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  const xml = new XMLSerializer().serializeToString(clone)
  const image = new Image()
  image.onload = () => {
    const canvas = document.createElement('canvas')
    canvas.width = width * 4
    canvas.height = height * 4
    const context = canvas.getContext('2d')
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    canvas.toBlob(blob => {
      const anchor = document.createElement('a')
      anchor.href = URL.createObjectURL(blob)
      anchor.download = `${task.value?.title || 'mindmap'}.png`
      anchor.click()
    }, 'image/png')
  }
  image.onerror = () => alert(`${i18n.global.t('mindmap.renderFail')}SVG -> PNG`)
  image.src = `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(xml)))}`
}
function startPan(event) {
  let lastX = event.clientX
  let lastY = event.clientY
  const move = currentEvent => {
    tx.value += currentEvent.clientX - lastX
    ty.value += currentEvent.clientY - lastY
    lastX = currentEvent.clientX
    lastY = currentEvent.clientY
  }
  const up = () => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

onMounted(reload)
onBeforeUnmount(() => {
  if (markmap) markmap.destroy()
})
</script>

<style scoped>
.mindmap-shell{display:grid;grid-template-columns:minmax(0,1fr) 300px;align-items:stretch;gap:14px}
.mindmap-shell.map-only,.mindmap-shell.text-only{grid-template-columns:1fr}
.view-mode-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;padding:7px 10px}
.view-mode-bar>span{padding-left:4px;color:var(--muted);font-size:11px;font-weight:600}
.map-surface{display:flex;min-width:0;height:calc(100dvh - 255px);min-height:520px;flex-direction:column;overflow:hidden}
.map-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:56px;padding:8px 12px;border-bottom:1px solid var(--border)}
.map-toolbar>strong{font-size:12px;color:var(--text-2)}
.view-tabs{display:flex;padding:3px;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--card-2)}
.view-tabs button{height:28px;padding:0 10px;border-radius:5px;color:var(--muted);font-size:11px}
.view-tabs button.active{background:var(--card);color:var(--accent);box-shadow:var(--shadow-sm);font-weight:600}
.map-controls{display:flex;align-items:center;gap:3px}
.zoom-value{min-width:44px;color:var(--muted);font-family:var(--mono);font-size:10.5px;text-align:center}
.map-viewport{position:relative;flex:1;min-height:0;overflow:hidden}
.map-grid{position:absolute;inset:0;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='22' height='22'%3E%3Ccircle cx='1' cy='1' r='1' fill='%23cfd6e2'/%3E%3C/svg%3E");background-size:22px 22px;opacity:.48}
:global([data-theme="dark"]) .map-grid{background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='22' height='22'%3E%3Ccircle cx='1' cy='1' r='1' fill='%233a4656'/%3E%3C/svg%3E")}
.mm-scaler{position:relative;width:100%;height:100%;transform-origin:center center;transition:transform var(--ease)}
.markmap{display:block;width:100%;height:100%;overflow:visible}
.map-state{position:absolute;inset:50% auto auto 50%;width:min(360px,calc(100% - 40px));transform:translate(-50%,-50%);box-shadow:var(--shadow)}
.outline-panel{display:flex;height:calc(100dvh - 255px);min-height:520px;flex-direction:column;overflow:hidden}
.outline-panel.full{grid-column:1 / -1}
.panel-head{display:flex;align-items:center;gap:7px;min-height:56px;padding:10px 14px;border-bottom:1px solid var(--border);color:var(--text-2);font-size:12px;font-weight:650}
.outline-pre{flex:1;margin:0;padding:15px;overflow:auto;white-space:pre-wrap;word-break:break-word;color:var(--text-2);font-family:var(--mono);font-size:11.5px;line-height:1.75}
.outline-empty{flex:1}
.export-panel{margin-top:14px;padding:0 18px 18px}
.export-panel :deep(.section-header){margin:0 -18px 14px;padding:15px 18px 12px;border-bottom:1px solid var(--border)}
.export-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.inline-note{color:var(--muted);font-size:11px}

@media (max-width:1050px){
  .mindmap-shell{grid-template-columns:minmax(0,1fr) 260px}
}
@media (max-width:899px){
  .mindmap-shell{grid-template-columns:1fr}
  .map-surface,.outline-panel{height:68dvh;min-height:540px}
}
@media (max-width:767px){
  .map-toolbar{align-items:flex-start;flex-direction:column}
  .map-controls{width:100%;overflow-x:auto;padding-bottom:2px}
}
</style>
