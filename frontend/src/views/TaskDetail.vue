<template>
  <div class="page page-wide task-detail">
    <PageHeader :title="task?.title || task?.source_url || id" :subtitle="$t('task.subtitle')" icon="console">
      <template #meta>
        <span v-if="task?.status" class="badge" :class="task.status">
          <span class="d"></span>{{ statusText(task.status) }}
        </span>
        <span class="mono-sm muted">{{ id }}</span>
      </template>
      <template #actions>
        <router-link v-if="task?.note_path" class="btn" :to="`/note/${id}`">
          <AppIcon name="notes" :size="16" />{{ $t('task.openNote') }}
        </router-link>
        <router-link v-if="task?.mindmap_paths?.length" class="btn" :to="`/mindmap/${id}`">
          <AppIcon name="mindmap" :size="16" />{{ $t('task.openMindmap') }}
        </router-link>
        <button
          v-if="task && (task.status === 'failed' || task.status === 'completed' || task.status === 'cancelled')"
          class="btn btn-primary"
          type="button"
          @click="rerun"
        >
          <AppIcon name="arrow-clockwise" :size="16" />{{ $t('task.rerun') }}
        </button>
        <button
          v-if="task && (task.status === 'running' || task.status === 'pending')"
          class="btn task-cancel"
          type="button"
          @click="cancel"
        >
          <AppIcon name="close" :size="16" />{{ $t('task.cancel') }}
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="loading" :label="$t('browser.loading')" :rows="7" />
    <EmptyState
      v-else-if="loadError"
      class="surface"
      :title="$t('task.loadErrorTitle')"
      :description="loadError"
      icon="warning"
      tone="danger"
    >
      <template #actions>
        <button class="btn" type="button" @click="reload">
          <AppIcon name="arrow-clockwise" :size="16" />{{ $t('browser.retry') }}
        </button>
      </template>
    </EmptyState>

    <template v-else>
      <section class="task-summary surface" aria-labelledby="task-current-title">
        <div class="current-step">
          <span class="summary-icon" :class="task.status">
            <AppIcon :name="summaryIcon" :size="22" weight="duotone" />
          </span>
          <div class="summary-copy">
            <span class="section-kicker">{{ $t('task.currentStep') }}</span>
            <h2 id="task-current-title">{{ currentTitle }}</h2>
            <p>{{ currentHint }}</p>
            <div class="summary-meta">
              <span>{{ $t('task.startedAt') }} {{ formatDate(task.created_at) }}</span>
              <span v-if="activeNode?.status === 'running'">{{ $t('task.keepOpenHint') }}</span>
            </div>
          </div>
        </div>

        <div
          class="progress-block"
          role="progressbar"
          :aria-label="$t('task.progressTitle')"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-valuenow="task?.progress || 0"
        >
          <div class="progress-ring">
            <svg viewBox="0 0 80 80" aria-hidden="true">
              <circle cx="40" cy="40" r="34" class="bg"/>
              <circle cx="40" cy="40" r="34" class="fg" :stroke-dasharray="ring.dash" :stroke-dashoffset="ring.off"/>
            </svg>
            <div class="ring-num">{{ task?.progress || 0 }}%</div>
          </div>
          <div class="progress-caption">
            <strong>{{ completedNodeCount }}/6</strong>
            <span>{{ $t('task.stepsFinished') }}</span>
          </div>
        </div>

        <div class="next-step">
          <span><AppIcon name="arrow-right" :size="16" />{{ $t('task.nextTitle') }}</span>
          <strong>{{ nextTitle }}</strong>
          <p>{{ nextHint }}</p>
        </div>
      </section>

      <section class="pipeline-surface surface">
        <SectionHeader :title="$t('task.pipelineTitle')" :description="$t('task.pipelineHint')" />
        <div class="pipeline-rail-wrap"><PipelineRail :nodes="nodeStatuses" /></div>
        <div class="node-list">
          <article v-for="node in nodeDetail" :key="node.key" class="node-row" :class="node.status">
            <span class="node-index">{{ node.index }}</span>
            <div class="node-copy">
              <strong>{{ $t(node.label) }}</strong>
              <small>{{ $t(`task.nodeHint.${node.key}`) }}</small>
            </div>
            <span class="badge" :class="node.status">
              <span class="d"></span>{{ statusText(node.status) }}
            </span>
            <span class="node-duration">{{ node.duration }}</span>
            <span class="product-label" :class="{ ready: node.productReady }" :title="node.product">
              <AppIcon :name="node.productReady ? 'check-circle' : 'tray'" :size="14" />
              {{ node.product }}
            </span>
          </article>
        </div>
      </section>

      <div class="detail-grid">
        <section class="artifact-panel surface">
          <SectionHeader :title="$t('task.artifactTitle')" :description="$t('task.artifactHint')" />
          <div class="artifact-tabs" role="tablist" :aria-label="$t('task.artifactTitle')">
            <button
              v-for="item in tabs"
              :id="`artifact-tab-${item.v}`"
              :key="item.v"
              :class="{ active: tab === item.v }"
              type="button"
              role="tab"
              :aria-controls="`artifact-panel-${item.v}`"
              :aria-selected="tab === item.v"
              @click="switchTab(item.v)"
            >
              <AppIcon :name="item.icon" :size="16" />
              {{ $t(item.l) }}
              <span v-if="item.v !== 'meta'" class="tab-state-dot" :class="artifactState(item.v)"></span>
            </button>
          </div>

          <div
            :id="`artifact-panel-${tab}`"
            class="tab-body"
            role="tabpanel"
            :aria-labelledby="`artifact-tab-${tab}`"
          >
            <LoadingState
              v-if="currentArtifact.state === 'loading'"
              class="artifact-loading"
              :label="$t('browser.loading')"
              :rows="5"
            />
            <EmptyState
              v-else-if="tab !== 'meta' && currentArtifact.state !== 'ready'"
              class="artifact-empty"
              :title="artifactEmptyTitle"
              :description="artifactEmptyHint"
              :icon="currentArtifact.state === 'error' ? 'warning' : 'tray'"
              :tone="currentArtifact.state === 'error' ? 'danger' : 'default'"
            >
              <template v-if="currentArtifact.state === 'error'" #actions>
                <button class="btn btn-sm" type="button" @click="loadTab(true)">
                  <AppIcon name="arrow-clockwise" :size="15" />{{ $t('browser.retry') }}
                </button>
              </template>
            </EmptyState>
            <div v-else-if="tab === 'srt'" class="transcript-list">
              <article v-for="(cue, cueIndex) in srtCues" :key="`${cue.start}-${cueIndex}`" class="transcript-cue">
                <time>{{ cue.start }}</time>
                <p>{{ cue.text }}</p>
              </article>
              <pre v-if="!srtCues.length" class="tab-pre">{{ currentArtifact.text }}</pre>
            </div>
            <article
              v-else-if="tab === 'note'"
              class="note-md note-preview"
              v-html="noteHtml"
              @error.capture="handleImageError"
            ></article>
            <dl v-else class="meta-list">
              <div v-for="row in metaRows" :key="row.k">
                <dt>{{ $t(row.k) }}</dt>
                <dd>{{ row.v }}</dd>
              </div>
            </dl>
          </div>
        </section>

        <section class="activity-panel surface">
          <SectionHeader :title="$t('task.activityTitle')" :description="$t('task.activityHint')" />
          <div class="activity-status">
            <span class="stream-dot" :class="streamStatus"></span>
            {{ $t(`task.stream.${streamStatus}`) }}
          </div>
          <ol v-if="activities.length" class="activity-list" aria-live="polite">
            <li v-for="item in activities" :key="item.id" :class="item.status">
              <span class="activity-icon">
                <AppIcon :name="activityIcon(item)" :size="16" />
              </span>
              <div>
                <strong>{{ activityTitle(item) }}</strong>
                <p>{{ activityDescription(item) }}</p>
                <time>{{ formatActivityTime(item.timestamp) }}</time>
              </div>
            </li>
          </ol>
          <EmptyState
            v-else
            class="activity-empty"
            :title="$t('task.activityEmpty')"
            :description="$t('task.activityEmptyHint')"
            icon="clock-history"
          />
        </section>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import PageHeader from '@/components/PageHeader.vue'
import PipelineRail from '@/components/PipelineRail.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import { cancelTask, getProductUrl, getTask, rerunTask, streamTask } from '@/api'
import { noteImageError, readProductText, rewriteTaskScreenshotLinks } from '@/artifacts'
import { i18n } from '@/i18n'
import { renderMarkdown } from '@/markdown'
import {
  eventLogText,
  snapshotActivities,
  upsertActivity,
} from '@/taskActivity'

const route = useRoute()
const id = String(route.params.id)
const task = ref({})
const activities = ref([])
const tab = ref('srt')
const products = ref({
  srt: { state: 'idle', text: '', error: '' },
  note: { state: 'idle', text: '', error: '' },
})
const loading = ref(true)
const loadError = ref('')
const streamStatus = ref('connecting')

const NODES = [
  ['download', 'pipeline.download', 'video'],
  ['extract_audio', 'pipeline.audio', 'audio'],
  ['asr', 'pipeline.asr', 'srt'],
  ['note', 'pipeline.note', 'note'],
  ['mindmap', 'pipeline.mindmap', 'mindmap'],
  ['cleanup', 'pipeline.cleanup', ''],
]
const tabs = [
  { v: 'srt', l: 'task.tabTranscript', icon: 'file-text' },
  { v: 'note', l: 'task.tabNote', icon: 'notes' },
  { v: 'meta', l: 'task.tabMeta', icon: 'sliders' },
]
const nodeStatuses = computed(() => task.value?.node_statuses || {})
const statusText = status => i18n.global.t(`status.${status || 'pending'}`)
const ring = computed(() => {
  const progress = (task.value?.progress || 0) / 100
  const circumference = 2 * Math.PI * 34
  return { dash: circumference, off: circumference * (1 - progress) }
})

function productOf(kind) {
  const currentTask = task.value || {}
  if (kind === 'video') return currentTask.video_path
  if (kind === 'audio') return currentTask.audio_path
  if (kind === 'srt') return currentTask.srt_path
  if (kind === 'note') return currentTask.note_path
  if (kind === 'mindmap') return (currentTask.mindmap_paths || [])[0] || ''
  return ''
}

const nodeDetail = computed(() => NODES.map(([key, label, kind], index) => {
  const node = (task.value?.node_statuses || {})[key] || {}
  const status = node.status || 'pending'
  const duration = node.started_at && node.finished_at
    ? durationBetween(node.started_at, node.finished_at)
    : (status === 'running' ? durationBetween(node.started_at, new Date().toISOString()) : '-')
  const path = productOf(kind)
  const size = node.product?.size_bytes
  let product = i18n.global.t('task.productWaiting')
  let productReady = false
  if (status === 'skipped') product = i18n.global.t('task.productSkipped')
  else if (!kind) product = status === 'completed' ? i18n.global.t('task.productNone') : i18n.global.t('task.productWaiting')
  else if (path) {
    product = `${baseName(path)}${size ? ` · ${formatBytes(size)}` : ''}`
    productReady = true
  } else if (status === 'completed') {
    product = i18n.global.t('task.productNone')
  }
  return {
    key,
    label,
    index: String(index + 1).padStart(2, '0'),
    status,
    duration,
    product,
    productReady,
  }
}))

const completedNodeCount = computed(() => nodeDetail.value.filter(node => ['completed', 'skipped'].includes(node.status)).length)
const activeNode = computed(() => (
  nodeDetail.value.find(node => node.status === 'failed')
  || nodeDetail.value.find(node => node.status === 'running')
  || nodeDetail.value.find(node => node.status === 'pending')
  || null
))
const activeNodeIndex = computed(() => activeNode.value ? NODES.findIndex(([key]) => key === activeNode.value.key) : -1)
const nextNode = computed(() => {
  if (['completed', 'failed', 'cancelled'].includes(task.value?.status)) return null
  const start = Math.max(0, activeNodeIndex.value + (activeNode.value?.status === 'running' ? 1 : 0))
  return nodeDetail.value.slice(start).find(node => !['completed', 'skipped', 'running'].includes(node.status)) || null
})
const summaryIcon = computed(() => ({
  completed: 'check-circle',
  failed: 'warning',
  cancelled: 'close',
  running: 'arrow-clockwise',
  pending: 'clock-history',
}[task.value?.status] || 'info'))
const currentTitle = computed(() => {
  if (task.value?.status === 'completed') return i18n.global.t('task.summaryCompleted')
  if (task.value?.status === 'failed') return i18n.global.t('task.summaryFailed')
  if (task.value?.status === 'cancelled') return i18n.global.t('task.summaryCancelled')
  if (task.value?.status === 'pending') return i18n.global.t('task.summaryQueued')
  return activeNode.value
    ? i18n.global.t(`task.nodeAction.${activeNode.value.key}`)
    : i18n.global.t('task.summaryRunning')
})
const currentHint = computed(() => {
  if (task.value?.status === 'failed') return task.value?.error || i18n.global.t('task.failedHint')
  if (task.value?.status === 'completed') return i18n.global.t('task.completedHint')
  if (task.value?.status === 'cancelled') return i18n.global.t('task.cancelledHint')
  if (task.value?.status === 'pending') return i18n.global.t('task.queuedHint')
  return activeNode.value
    ? i18n.global.t(`task.nodeHint.${activeNode.value.key}`)
    : i18n.global.t('task.progressHint')
})
const nextTitle = computed(() => {
  if (task.value?.status === 'completed') return i18n.global.t('task.nextRead')
  if (task.value?.status === 'failed') return i18n.global.t('task.nextRetry')
  if (task.value?.status === 'cancelled') return i18n.global.t('task.nextRetry')
  return nextNode.value ? i18n.global.t(nextNode.value.label) : i18n.global.t('task.nextFinish')
})
const nextHint = computed(() => {
  if (task.value?.status === 'completed') return i18n.global.t('task.nextReadHint')
  if (['failed', 'cancelled'].includes(task.value?.status)) return i18n.global.t('task.nextRetryHint')
  if (!nextNode.value) return i18n.global.t('task.nextFinishHint')
  return i18n.global.t(`task.nodeHint.${nextNode.value.key}`)
})

const currentArtifact = computed(() => {
  if (tab.value === 'meta') return { state: 'ready', text: '', error: '' }
  return products.value[tab.value]
})
const noteHtml = computed(() => renderMarkdown(
  rewriteTaskScreenshotLinks(
    products.value.note.text,
    id,
    task.value?.screenshot_paths || [],
  ),
))
const srtCues = computed(() => parseSrt(products.value.srt.text))
const artifactEmptyTitle = computed(() => {
  if (currentArtifact.value.state === 'error') return i18n.global.t('task.productLoadError')
  if (currentArtifact.value.state === 'missing') return i18n.global.t('task.productRemoved')
  return tab.value === 'srt'
    ? i18n.global.t('task.transcriptPending')
    : i18n.global.t('task.notePending')
})
const artifactEmptyHint = computed(() => {
  if (currentArtifact.value.state === 'error') return currentArtifact.value.error
  if (currentArtifact.value.state === 'missing') return i18n.global.t('task.productRemovedHint')
  const nodeKey = tab.value === 'srt' ? 'asr' : 'note'
  const status = task.value?.node_statuses?.[nodeKey]?.status || 'pending'
  return status === 'running'
    ? i18n.global.t(`task.nodeHint.${nodeKey}`)
    : i18n.global.t('task.productPendingHint')
})
const metaRows = computed(() => {
  const currentTask = task.value || {}
  return [
    { k: 'task.metaId', v: currentTask.id },
    { k: 'task.metaSource', v: currentTask.source_url || currentTask.source_type },
    { k: 'task.metaAsr', v: i18n.global.t(`engine.short.${currentTask.asr_engine || 'bcut'}`) },
    { k: 'task.metaLlm', v: `${currentTask.llm_provider || ''}/${currentTask.llm_model || ''}` },
    { k: 'task.metaLang', v: currentTask.output_language },
    { k: 'task.metaDetail', v: currentTask.note_detail_level ? i18n.global.t(`settings.detail.${currentTask.note_detail_level}`) : '' },
    { k: 'task.metaShot', v: currentTask.extract_images ? i18n.global.t('task.shotOn') : i18n.global.t('task.shotOff') },
    { k: 'task.metaShotCount', v: String((currentTask.screenshot_paths || []).length) },
    { k: 'task.metaCreated', v: formatDate(currentTask.created_at) },
    { k: 'task.metaFinished', v: formatDate(currentTask.finished_at) },
    { k: 'task.metaError', v: currentTask.error || '' },
  ].filter(row => row.v)
})

function durationBetween(start, end) {
  if (!start || !end) return '-'
  const seconds = Math.max(0, Math.round((new Date(end) - new Date(start)) / 1000))
  if (!Number.isFinite(seconds)) return '-'
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}
function baseName(path) {
  return path ? String(path).split('/').pop() : ''
}
function formatBytes(bytes) {
  const value = Number(bytes || 0)
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
function formatDate(date) {
  return date ? String(date).replace('T', ' ').slice(0, 19) : '-'
}
function formatActivityTime(timestamp) {
  if (!timestamp) return i18n.global.t('task.timeUnknown')
  const date = typeof timestamp === 'number' ? new Date(timestamp * 1000) : new Date(timestamp)
  return Number.isNaN(date.getTime()) ? i18n.global.t('task.timeUnknown') : date.toLocaleTimeString()
}
function parseSrt(text) {
  return String(text || '').split(/\r?\n\s*\r?\n/).map(block => {
    const lines = block.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
    const timeIndex = lines.findIndex(line => line.includes('-->'))
    if (timeIndex < 0) return null
    const [start, end] = lines[timeIndex].split('-->').map(value => value.trim().replace(',', '.'))
    return { start, end, text: lines.slice(timeIndex + 1).join(' ') }
  }).filter(cue => cue?.text)
}
function artifactState(kind) {
  if (kind === 'srt' && task.value?.srt_path) return 'ready'
  if (kind === 'note' && task.value?.note_path) return 'ready'
  return products.value[kind]?.state || 'idle'
}
function handleImageError(event) {
  noteImageError(event, i18n.global.t('note.imageUnavailable'))
}

function activityIcon(item) {
  if (item.status === 'completed') return 'check-circle'
  if (item.status === 'failed') return 'warning'
  if (item.status === 'running') return 'arrow-clockwise'
  if (item.status === 'skipped') return 'arrow-right'
  return 'info'
}
function activityTitle(item) {
  if (item.kind === 'log') return i18n.global.t('task.activityUpdate')
  if (item.kind === 'progress') return i18n.global.t('task.activityProgress', { node: i18n.global.t(`pipeline.${nodeLabelKey(item.node)}`) })
  const node = i18n.global.t(`pipeline.${nodeLabelKey(item.node)}`)
  return i18n.global.t(`task.activityState.${item.status}`, { node })
}
function activityDescription(item) {
  if (item.message) return item.message
  if (item.error) return item.error
  return i18n.global.t(`task.nodeHint.${item.node}`)
}
function nodeLabelKey(node) {
  return { extract_audio: 'audio', asr: 'asr' }[node] || node
}
function syncSnapshotActivity(nextTask) {
  snapshotActivities(nextTask).forEach(item => {
    activities.value = upsertActivity(activities.value, item)
  })
}
function appendActivity(item) {
  activities.value = upsertActivity(activities.value, item)
}
function eventData(event) {
  try {
    return JSON.parse(event.data)
  } catch {
    return {}
  }
}
function eventTimestamp(data) {
  return data?.payload?.ts || data?.ts || new Date().toISOString()
}
function updateNode(node, updates) {
  if (!node) return
  const current = task.value?.node_statuses?.[node] || {}
  task.value.node_statuses = {
    ...(task.value.node_statuses || {}),
    [node]: { ...current, ...updates },
  }
}

let eventSource
let refreshTimer
async function load(initial = false) {
  try {
    const nextTask = await getTask(id)
    task.value = nextTask
    syncSnapshotActivity(nextTask)
    if (initial) loadError.value = ''
    if (
      tab.value !== 'meta'
      && artifactAvailable(tab.value)
      && ['idle', 'unavailable', 'missing'].includes(products.value[tab.value].state)
    ) {
      await loadTab()
    }
    return true
  } catch (error) {
    if (initial) loadError.value = error?.message || i18n.global.t('task.loadFail')
    return false
  }
}
function artifactAvailable(kind) {
  return kind === 'srt' ? Boolean(task.value?.srt_path) : Boolean(task.value?.note_path)
}
async function loadTab(force = false) {
  const kind = tab.value
  if (kind === 'meta') return
  if (!force && products.value[kind].state === 'ready') return
  products.value[kind] = {
    state: artifactAvailable(kind) ? 'loading' : 'unavailable',
    text: '',
    error: '',
  }
  if (!artifactAvailable(kind)) return
  try {
    const result = await readProductText({
      url: getProductUrl(id, kind),
      available: true,
    })
    products.value[kind] = { ...result, error: '' }
  } catch (error) {
    products.value[kind] = {
      state: 'error',
      text: '',
      error: error?.message || i18n.global.t('task.loadFail'),
    }
  }
}
function switchTab(value) {
  tab.value = value
  loadTab()
}
async function reload() {
  loading.value = true
  const loaded = await load(true)
  if (loaded) {
    await loadTab(true)
    openStream()
  }
  loading.value = false
}
function openStream() {
  if (eventSource) eventSource.close()
  streamStatus.value = 'connecting'
  eventSource = streamTask(id)
  eventSource.onopen = () => { streamStatus.value = 'live' }
  eventSource.onerror = () => {
    if (!['completed', 'failed', 'cancelled'].includes(task.value?.status)) {
      streamStatus.value = 'reconnecting'
    }
  }
  eventSource.addEventListener('snapshot', event => {
    const data = eventData(event)
    if (data.payload) {
      task.value = { ...task.value, ...data.payload }
      syncSnapshotActivity(task.value)
    }
    streamStatus.value = 'live'
  })
  eventSource.addEventListener('node-entered', event => {
    const data = eventData(event)
    const node = data.payload?.node
    const timestamp = eventTimestamp(data)
    updateNode(node, { status: 'running', started_at: data.payload?.ts || new Date().toISOString() })
    appendActivity({ id: `node:${node}:running`, node, status: 'running', timestamp, source: 'live' })
  })
  eventSource.addEventListener('node-progress', event => {
    const data = eventData(event)
    const node = data.payload?.node
    const progress = data.payload?.progress
    updateNode(node, { status: 'running', progress })
    appendActivity({
      id: `progress:${node}`,
      node,
      status: 'running',
      kind: 'progress',
      message: data.payload?.message || i18n.global.t('task.progressPercent', { progress }),
      timestamp: eventTimestamp(data),
    })
  })
  eventSource.addEventListener('node-product', event => {
    const data = eventData(event)
    const { node, kind, path, size_bytes: size } = data.payload || {}
    updateNode(node, { product: { path, size_bytes: size } })
    if (kind === 'srt') task.value.srt_path = path
    if (kind === 'note') task.value.note_path = path
    if (kind === 'screenshot') task.value.screenshot_paths = [...(task.value.screenshot_paths || []), path]
    appendActivity({
      id: `product:${kind}:${path}`,
      node,
      status: 'completed',
      message: i18n.global.t('task.activityProduct', { product: baseName(path) }),
      timestamp: eventTimestamp(data),
    })
    if (tab.value === kind) loadTab(true)
  })
  eventSource.addEventListener('node-completed', event => {
    const data = eventData(event)
    const node = data.payload?.node
    const timestamp = eventTimestamp(data)
    updateNode(node, { status: 'completed', progress: 100, finished_at: data.payload?.ts || new Date().toISOString() })
    appendActivity({ id: `node:${node}:completed`, node, status: 'completed', timestamp, source: 'live' })
  })
  eventSource.addEventListener('node-failed', event => {
    const data = eventData(event)
    const node = data.payload?.node
    updateNode(node, { status: 'failed', error: data.payload?.error })
    appendActivity({
      id: `node:${node}:failed`,
      node,
      status: 'failed',
      error: data.payload?.error,
      timestamp: eventTimestamp(data),
      source: 'live',
    })
  })
  eventSource.addEventListener('log', event => {
    const data = eventData(event)
    const text = eventLogText(data.payload)
    if (!text) return
    const timestamp = eventTimestamp(data)
    appendActivity({
      id: `log:${timestamp}:${text}`,
      kind: 'log',
      status: data.payload?.level === 'error' ? 'failed' : (data.payload?.level === 'ok' ? 'completed' : 'running'),
      message: text,
      timestamp,
    })
  })
  eventSource.addEventListener('task-completed', async () => {
    task.value.status = 'completed'
    task.value.progress = 100
    streamStatus.value = 'closed'
    eventSource.close()
    await load(false)
    await loadTab(true)
  })
  eventSource.addEventListener('task-failed', async event => {
    const data = eventData(event)
    task.value.status = 'failed'
    task.value.error = data.payload?.error || task.value.error
    streamStatus.value = 'closed'
    eventSource.close()
    await load(false)
  })
  eventSource.addEventListener('task-cancelled', async () => {
    task.value.status = 'cancelled'
    streamStatus.value = 'closed'
    eventSource.close()
    await load(false)
  })
}
async function rerun() {
  await rerunTask(id)
  activities.value = []
  products.value = {
    srt: { state: 'idle', text: '', error: '' },
    note: { state: 'idle', text: '', error: '' },
  }
  await load()
  openStream()
}
async function cancel() {
  await cancelTask(id)
  await load()
}

onMounted(async () => {
  const loaded = await load(true)
  if (loaded) {
    await loadTab()
    openStream()
  }
  loading.value = false
  refreshTimer = setInterval(() => load(false), 3000)
})
onUnmounted(() => {
  if (eventSource) eventSource.close()
  clearInterval(refreshTimer)
})
</script>

<style scoped>
.task-cancel{border-color:color-mix(in srgb,var(--danger) 35%,var(--border));color:var(--danger)}
.task-cancel:hover{background:var(--danger-soft)}
.task-summary{display:grid;grid-template-columns:minmax(0,1fr) 180px minmax(220px,.7fr);align-items:center;gap:24px;margin-bottom:14px;padding:22px}
.current-step{display:flex;align-items:flex-start;gap:14px;min-width:0}
.summary-icon{display:flex;width:42px;height:42px;flex:none;align-items:center;justify-content:center;border:1px solid var(--border);border-radius:var(--r);background:var(--card-2);color:var(--muted)}
.summary-icon.running{border-color:color-mix(in srgb,var(--accent) 35%,var(--border));background:var(--accent-soft);color:var(--accent)}
.summary-icon.completed{border-color:color-mix(in srgb,var(--success) 35%,var(--border));background:var(--success-soft);color:var(--success)}
.summary-icon.failed,.summary-icon.cancelled{border-color:color-mix(in srgb,var(--danger) 35%,var(--border));background:var(--danger-soft);color:var(--danger)}
.summary-copy{min-width:0}.summary-copy h2{margin:4px 0 5px;font-size:19px;line-height:1.3}.summary-copy p{max-width:620px;margin:0;color:var(--text-2);font-size:12.5px;line-height:1.6}
.summary-meta{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px;color:var(--muted);font-family:var(--mono);font-size:9.5px}
.section-kicker{color:var(--accent);font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
.progress-block{display:flex;align-items:center;justify-content:center;gap:12px;padding:0 22px;border-right:1px solid var(--border);border-left:1px solid var(--border)}
.progress-ring{position:relative;width:74px;height:74px;flex:none}
.progress-ring svg{width:100%;height:100%;transform:rotate(-90deg)}
.progress-ring circle{fill:none;stroke-width:7}
.progress-ring circle.bg{stroke:var(--border)}
.progress-ring circle.fg{stroke:var(--accent);stroke-linecap:round;transition:stroke-dashoffset .3s}
.ring-num{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:13px;font-weight:700}
.progress-caption strong,.progress-caption span{display:block}.progress-caption strong{font-family:var(--mono);font-size:15px}.progress-caption span{margin-top:2px;color:var(--muted);font-size:10px}
.next-step{min-width:0}.next-step>span{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:10px;font-weight:650}.next-step strong{display:block;margin:6px 0 3px;font-size:13px}.next-step p{margin:0;color:var(--muted);font-size:10.5px;line-height:1.5}
.pipeline-surface{margin-bottom:14px;overflow:hidden}
.pipeline-surface :deep(.section-header){padding:16px 18px 8px}
.pipeline-rail-wrap{padding:8px 18px 12px}
.node-list{display:flex;flex-direction:column;border-top:1px solid var(--border)}
.node-row{display:grid;grid-template-columns:34px minmax(170px,1.1fr) 90px 78px minmax(180px,1fr);align-items:center;gap:12px;min-height:54px;padding:7px 18px;border-bottom:1px solid var(--border-2)}
.node-row:last-child{border-bottom:0}.node-row.running{background:var(--accent-soft)}.node-row.failed{background:var(--danger-soft)}
.node-index{color:var(--muted);font-family:var(--mono);font-size:10px}
.node-copy{min-width:0}.node-copy strong,.node-copy small{display:block}.node-copy strong{font-size:12px}.node-copy small{margin-top:2px;overflow:hidden;color:var(--muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}
.node-duration{color:var(--muted);font-family:var(--mono);font-size:10px}
.product-label{display:flex;min-width:0;align-items:center;gap:6px;overflow:hidden;color:var(--muted);font-family:var(--mono);font-size:9.5px;text-overflow:ellipsis;white-space:nowrap}
.product-label.ready{color:var(--success)}
.detail-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(320px,.65fr);gap:14px}
.artifact-panel,.activity-panel{min-width:0;overflow:hidden}
.artifact-panel :deep(.section-header),.activity-panel :deep(.section-header){padding:16px 18px 12px}
.artifact-tabs{display:flex;gap:4px;padding:0 18px;border-bottom:1px solid var(--border)}
.artifact-tabs button{display:flex;position:relative;align-items:center;gap:7px;min-height:41px;padding:0 10px;border-bottom:2px solid transparent;color:var(--muted);font-size:11px;font-weight:600}
.artifact-tabs button:hover{color:var(--text)}.artifact-tabs button:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.artifact-tabs button.active{border-bottom-color:var(--accent);color:var(--accent)}
.tab-state-dot{width:6px;height:6px;border-radius:50%;background:var(--border)}.tab-state-dot.ready{background:var(--success)}.tab-state-dot.loading{background:var(--accent)}
.tab-body{min-height:430px;max-height:640px;padding:18px;overflow:auto}
.artifact-loading{border:0;box-shadow:none}.artifact-empty{min-height:350px;border:0;box-shadow:none}
.transcript-list{display:flex;flex-direction:column}.transcript-cue{display:grid;grid-template-columns:104px minmax(0,1fr);gap:14px;padding:10px 0;border-bottom:1px solid var(--border-2)}
.transcript-cue time{color:var(--accent);font-family:var(--mono);font-size:10px}.transcript-cue p{margin:0;color:var(--text-2);font-size:12px;line-height:1.65}
.tab-pre{margin:0;white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:12px}
.note-preview{font-size:14px}.note-preview :deep(h2){font-size:23px}
.meta-list{display:flex;margin:0;flex-direction:column}.meta-list>div{display:grid;grid-template-columns:128px minmax(0,1fr);gap:12px;padding:10px 0;border-bottom:1px solid var(--border-2)}
.meta-list dt{color:var(--muted);font-size:10.5px}.meta-list dd{margin:0;overflow-wrap:anywhere;color:var(--text-2);font-family:var(--mono);font-size:11px}
.activity-status{display:flex;align-items:center;gap:7px;margin:0 18px 4px;color:var(--muted);font-size:10px}.stream-dot{width:7px;height:7px;border-radius:50%;background:var(--muted)}.stream-dot.live{background:var(--success)}.stream-dot.connecting,.stream-dot.reconnecting{background:var(--accent)}.stream-dot.closed{background:var(--muted)}
.activity-list{display:flex;max-height:588px;margin:0;padding:8px 18px 18px;overflow:auto;flex-direction:column;list-style:none}
.activity-list li{display:grid;grid-template-columns:30px minmax(0,1fr);gap:10px;padding:10px 0;border-bottom:1px solid var(--border-2)}
.activity-list li:last-child{border-bottom:0}.activity-icon{display:flex;width:28px;height:28px;align-items:center;justify-content:center;border-radius:50%;background:var(--card-2);color:var(--muted)}
.activity-list li.running .activity-icon{background:var(--accent-soft);color:var(--accent)}.activity-list li.completed .activity-icon{background:var(--success-soft);color:var(--success)}.activity-list li.failed .activity-icon{background:var(--danger-soft);color:var(--danger)}
.activity-list strong{display:block;font-size:11.5px}.activity-list p{margin:3px 0;color:var(--text-2);font-size:10.5px;line-height:1.5}.activity-list time{color:var(--muted);font-family:var(--mono);font-size:9px}
.activity-empty{min-height:350px;border:0;box-shadow:none}

@media (max-width:1179px){
  .task-summary{grid-template-columns:minmax(0,1fr) 170px}.next-step{grid-column:1/-1;padding-top:14px;border-top:1px solid var(--border)}
  .detail-grid{grid-template-columns:1fr}.activity-list{max-height:420px}
}
@media (max-width:899px){
  .node-row{grid-template-columns:28px minmax(150px,1fr) 88px 62px}.product-label{grid-column:2/-1;padding-bottom:4px}
}
@media (max-width:767px){
  .task-summary{grid-template-columns:1fr;padding:16px}.progress-block{justify-content:flex-start;padding:16px 0;border:0;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}.next-step{grid-column:auto;padding-top:0;border-top:0}
  .pipeline-rail-wrap{overflow-x:auto}.node-row{grid-template-columns:28px minmax(0,1fr) 86px;padding:10px 14px}.node-duration{grid-column:2}.product-label{grid-column:2/-1}.node-copy small{white-space:normal}
  .artifact-tabs{overflow-x:auto;padding:0 12px}.tab-body{min-height:350px;padding:14px}.transcript-cue{grid-template-columns:1fr;gap:4px}
  .meta-list>div{grid-template-columns:94px minmax(0,1fr)}
}
@media (prefers-reduced-motion:reduce){
  .progress-ring circle.fg{transition:none}
}
</style>
