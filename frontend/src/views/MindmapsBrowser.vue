<template>
  <div class="page-workspace mindmap-library">
    <PageHeader :title="$t('mindmap.libraryTitle')" :subtitle="$t('mindmap.librarySubtitle')" icon="mindmap">
      <template #actions>
        <button
          class="btn workspace-toggle toggle-library"
          type="button"
          :aria-pressed="libraryOpen"
          @click="libraryOpen = !libraryOpen"
        >
          <AppIcon name="sidebar" :size="17" />
          {{ $t('browser.library') }}
        </button>
        <button
          class="btn workspace-toggle toggle-context"
          type="button"
          :aria-pressed="contextOpen"
          @click="contextOpen = !contextOpen"
        >
          <AppIcon name="book-open" :size="17" />
          {{ $t('mindmap.outlineTitle') }}
        </button>
      </template>
    </PageHeader>

    <div class="library-workspace" :class="{ 'library-visible': libraryOpen, 'context-visible': contextOpen }">
      <LibrarySidebar
        v-model:query="q"
        :title="$t('mindmap.libraryList')"
        :items="items"
        :selected-id="selectedId"
        :loading="listLoading"
        :error="listError"
        item-icon="mindmap"
        :search-placeholder="$t('history.searchPh')"
        :loading-label="$t('browser.loading')"
        :empty-title="$t('mindmap.emptyLibrary')"
        :empty-description="$t('mindmap.emptyLibraryHint')"
        :error-title="$t('browser.loadError')"
        :retry-label="$t('browser.retry')"
        @update:query="debounced"
        @select="select"
        @retry="reload"
      />

      <main class="map-panel surface">
        <template v-if="selectedId">
          <div class="map-toolbar">
            <div class="map-heading">
              <strong>{{ task ? displayName(task) : $t('mindmap.title') }}</strong>
              <small>{{ Math.round(scale * 100) }}%</small>
            </div>
            <div class="map-controls" role="toolbar" :aria-label="$t('mindmap.viewControls')">
              <button class="icon-btn" type="button" :title="$t('mindmap.zoomIn')" :aria-label="$t('mindmap.zoomIn')" @click="zoomBy(0.2)"><AppIcon name="zoom-in" :size="17" /></button>
              <button class="icon-btn" type="button" :title="$t('mindmap.zoomOut')" :aria-label="$t('mindmap.zoomOut')" @click="zoomBy(-0.2)"><AppIcon name="zoom-out" :size="17" /></button>
              <span class="toolbar-divider"></span>
              <button class="icon-btn" type="button" :title="$t('mindmap.panUp')" :aria-label="$t('mindmap.panUp')" @click="pan(0, -60)"><AppIcon name="arrow-up" :size="16" /></button>
              <button class="icon-btn" type="button" :title="$t('mindmap.panDown')" :aria-label="$t('mindmap.panDown')" @click="pan(0, 60)"><AppIcon name="arrow-down" :size="16" /></button>
              <button class="icon-btn" type="button" :title="$t('mindmap.panLeft')" :aria-label="$t('mindmap.panLeft')" @click="pan(-60, 0)"><AppIcon name="arrow-left" :size="16" /></button>
              <button class="icon-btn" type="button" :title="$t('mindmap.panRight')" :aria-label="$t('mindmap.panRight')" @click="pan(60, 0)"><AppIcon name="arrow-right" :size="16" /></button>
              <span class="toolbar-divider"></span>
              <button class="btn btn-sm" type="button" @click="fit"><AppIcon name="arrows-out" :size="16" />{{ $t('mindmap.fit') }}</button>
            </div>
          </div>
          <div class="map-viewport" @mousedown.middle.prevent="startPan" @wheel.prevent="onWheel">
            <div class="map-grid" aria-hidden="true"></div>
            <div class="mm-scaler" :style="{ transform: `translate(${tx}px, ${ty}px) scale(${scale})` }">
              <svg ref="svgRef" class="markmap"></svg>
            </div>
            <LoadingState v-if="mapLoading && !errMsg" class="map-state" :label="$t('mindmap.rendering')" :rows="4" />
            <EmptyState
              v-else-if="errMsg"
              class="map-state"
              :title="$t('mindmap.renderErrorTitle')"
              :description="errMsg"
              icon="warning"
              tone="danger"
            >
              <template #actions>
                <button class="btn btn-sm" type="button" @click="select(selectedId)">
                  <AppIcon name="arrow-clockwise" :size="15" />
                  {{ $t('browser.retry') }}
                </button>
              </template>
            </EmptyState>
          </div>
        </template>
        <EmptyState
          v-else
          class="map-empty"
          :title="$t('mindmap.selectTitle')"
          :description="$t('mindmap.selectHint')"
          icon="mindmap"
        />
      </main>

      <aside class="context-panel surface">
        <div class="context-tabs">
          <button :class="{ active: tab === 'outline' }" type="button" @click="tab = 'outline'">{{ $t('mindmap.outlineTitle') }}</button>
          <button :class="{ active: tab === 'action' }" type="button" @click="tab = 'action'">{{ $t('browser.action') }}</button>
        </div>
        <div v-if="tab === 'outline'" class="context-body">
          <pre v-if="outline" class="outline-pre">{{ outline }}</pre>
          <EmptyState
            v-else
            class="context-empty"
            :title="$t('mindmap.noOutline')"
            :description="$t('mindmap.noOutlineHint')"
            icon="book-open"
          />
        </div>
        <div v-else class="context-body action-stack">
          <a
            v-for="entry in hrefEntries"
            :key="entry.fmt"
            class="btn"
            :href="mindmapUrl(entry.i)"
            :download="`mindmap.${entry.fmt}`"
          >
            <AppIcon name="download" :size="16" />
            {{ $t(exportLabel(entry.fmt)) }}
          </a>
          <button class="btn" type="button" :disabled="!ready" @click="exportPng"><AppIcon name="download" :size="16" />{{ $t('mindmap.exportPng') }}</button>
          <router-link class="btn btn-primary" :to="`/notes?id=${selectedId}`"><AppIcon name="notes" :size="16" />{{ $t('note.title') }}</router-link>
          <div v-if="!exportEntries.length" class="inline-note">{{ $t('mindmap.noMap') }}</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import LibrarySidebar from '@/components/LibrarySidebar.vue'
import LoadingState from '@/components/LoadingState.vue'
import PageHeader from '@/components/PageHeader.vue'
import { getProductUrl, getTask, listTasks } from '@/api'
import { displayName } from '@/format'
import { i18n } from '@/i18n'

const route = useRoute()
const router = useRouter()
const items = ref([])
const q = ref('')
const selectedId = ref('')
const task = ref(null)
const svgRef = ref(null)
const ready = ref(false)
const errMsg = ref('')
const mapLoading = ref(false)
const listLoading = ref(true)
const listError = ref('')
const scale = ref(1)
const tx = ref(0)
const ty = ref(0)
const outline = ref('')
const tab = ref('outline')
const libraryOpen = ref(false)
const contextOpen = ref(false)
let markmap
let debounceTimer

const formats = computed(() => task.value?.mindmap_formats || [])
const exportEntries = computed(() => formats.value.map((format, index) => ({ fmt: format, i: index })))
const hrefEntries = computed(() => exportEntries.value.filter(entry => entry.fmt !== 'png'))

function exportLabel(format) {
  return { xmind: 'mindmap.exportXmind', png: 'mindmap.exportPng', md: 'mindmap.exportMd' }[format] || format
}
function mindmapUrl(index) {
  return selectedId.value ? `${getProductUrl(selectedId.value, 'mindmap')}?index=${index}` : ''
}
async function reload() {
  listLoading.value = true
  listError.value = ''
  try {
    const response = await listTasks({ status: 'completed', q: q.value || undefined, page: 1, page_size: 100 })
    items.value = response.items || []
    const requestedId = route.query.id ? String(route.query.id) : ''
    const nextId = requestedId || selectedId.value || String(items.value[0]?.id || '')
    if (nextId && items.value.some(item => String(item.id) === nextId)) await select(nextId)
    else if (!items.value.length) {
      selectedId.value = ''
      task.value = null
      outline.value = ''
    }
  } catch (error) {
    listError.value = error.message
  } finally {
    listLoading.value = false
  }
}
function debounced(value) {
  q.value = value
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(reload, 300)
}
async function select(id) {
  const nextId = String(id)
  selectedId.value = nextId
  tab.value = 'outline'
  ready.value = false
  errMsg.value = ''
  mapLoading.value = true
  scale.value = 1
  tx.value = 0
  ty.value = 0
  router.replace({ query: { ...route.query, id: nextId } }).catch(() => {})
  if (markmap) markmap.destroy()
  markmap = null
  await nextTick()
  try {
    task.value = await getTask(nextId)
    await Promise.all([renderMap(nextId), loadOutline(nextId)])
  } catch (error) {
    task.value = null
    errMsg.value = error.message
  } finally {
    mapLoading.value = false
  }
}
async function fetchNote(id) {
  const response = await fetch(getProductUrl(id, 'note'))
  if (!response.ok) throw new Error(i18n.global.t('mindmap.noteNotReady'))
  return await response.text()
}
async function renderMap(id) {
  try {
    const markdown = await fetchNote(id)
    const [{ Transformer }, { Markmap }] = await Promise.all([import('markmap-lib'), import('markmap-view')])
    const { root } = new Transformer().transform(markdown)
    markmap = Markmap.create(svgRef.value, { initialExpandLevel: -1, zoom: false, duration: 220, padding: 18 }, root)
    ready.value = true
  } catch (error) {
    errMsg.value = i18n.global.t('mindmap.renderFail') + error.message
  }
}
async function loadOutline(id) {
  try {
    outline.value = outlineFromNote(await fetchNote(id))
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
function zoomBy(delta) {
  scale.value = Math.min(3, Math.max(0.2, +(scale.value + delta).toFixed(2)))
}
function onWheel(event) {
  const factor = Math.exp(-event.deltaY * 0.001)
  scale.value = Math.min(3, Math.max(0.2, +(scale.value * factor).toFixed(3)))
}
function pan(dx, dy) {
  tx.value += dx
  ty.value += dy
}
function fit() {
  scale.value = 1
  tx.value = 0
  ty.value = 0
  if (markmap) markmap.fit()
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
  clearTimeout(debounceTimer)
})
</script>

<style scoped>
.library-workspace{position:relative;display:grid;grid-template-columns:minmax(220px,250px) minmax(0,1fr) minmax(250px,280px);gap:12px;height:calc(100dvh - 170px);min-height:560px}
.map-panel,.context-panel{display:flex;min-width:0;min-height:0;flex-direction:column;overflow:hidden}
.map-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:57px;padding:9px 12px;border-bottom:1px solid var(--border)}
.map-heading{min-width:0}.map-heading strong,.map-heading small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.map-heading strong{font-size:12.5px}.map-heading small{margin-top:2px;color:var(--muted);font-family:var(--mono);font-size:10px}
.map-controls{display:flex;align-items:center;gap:3px}
.toolbar-divider{width:1px;height:22px;margin:0 4px;background:var(--border)}
.map-viewport{position:relative;flex:1;min-height:0;overflow:hidden;background:var(--card)}
.map-grid{position:absolute;inset:0;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='22' height='22'%3E%3Ccircle cx='1' cy='1' r='1' fill='%23cfd6e2'/%3E%3C/svg%3E");background-size:22px 22px;opacity:.48}
:global([data-theme="dark"]) .map-grid{background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='22' height='22'%3E%3Ccircle cx='1' cy='1' r='1' fill='%233a4656'/%3E%3C/svg%3E")}
.mm-scaler{position:relative;width:100%;height:100%;transform-origin:center center;transition:transform var(--ease)}
.markmap{display:block;width:100%;height:100%;overflow:visible}
.map-state{position:absolute;inset:50% auto auto 50%;width:min(360px,calc(100% - 40px));transform:translate(-50%,-50%);box-shadow:var(--shadow)}
.map-empty{flex:1}
.context-tabs{display:grid;grid-template-columns:1fr 1fr;padding:7px;border-bottom:1px solid var(--border)}
.context-tabs button{height:32px;border-radius:var(--r-sm);color:var(--muted);font-size:12px;font-weight:600}
.context-tabs button:hover{background:var(--card-2);color:var(--text)}
.context-tabs button.active{background:var(--accent-soft);color:var(--accent)}
.context-body{flex:1;min-height:0;overflow:auto;padding:12px}
.outline-pre{margin:0;white-space:pre-wrap;word-break:break-word;color:var(--text-2);font-family:var(--mono);font-size:11.5px;line-height:1.75}
.context-empty{min-height:260px;padding:18px}
.action-stack{display:flex;flex-direction:column;gap:7px}
.inline-note{margin-top:5px;padding:10px;border-radius:var(--r-sm);background:var(--card-2);color:var(--muted);font-size:11px;line-height:1.5}
.workspace-toggle{display:none}

@media (max-width:1179px){
  .library-workspace{grid-template-columns:240px minmax(0,1fr)}
  .context-panel{display:none}
  .context-visible .map-panel{display:none}
  .context-visible .context-panel{display:flex;grid-column:2}
  .toggle-context{display:inline-flex}
}
@media (max-width:899px){
  .library-workspace{grid-template-columns:1fr;height:auto;min-height:620px}
  .library-workspace :deep(.library-sidebar){display:none;height:420px}
  .library-visible :deep(.library-sidebar){display:flex}
  .library-visible .map-panel,.library-visible .context-panel{display:none}
  .context-visible .context-panel{display:flex;grid-column:1;min-height:620px}
  .context-visible .map-panel{display:none}
  .toggle-library{display:inline-flex}
  .map-panel{min-height:620px}
}
@media (max-width:767px){
  .map-toolbar{align-items:flex-start;flex-direction:column}
  .map-controls{width:100%;overflow-x:auto;padding-bottom:2px}
}
</style>
