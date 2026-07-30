<template>
  <div class="page page-wide history-page">
    <PageHeader :title="$t('history.title')" :subtitle="$t('history.subtitle')" icon="clock-history">
      <template #meta>
        <div class="history-summary">
          <span>{{ $t('history.totalCount', { count: total }) }}</span>
          <span v-if="selected.length">{{ $t('history.selectedCount', { count: selected.length }) }}</span>
        </div>
      </template>
    </PageHeader>

    <section class="filter-panel surface">
      <div class="filter-search">
        <label>
          <span>{{ $t('history.searchLabel') }}</span>
          <div class="search">
            <AppIcon name="search" :size="16" />
            <input v-model="q" :placeholder="$t('history.searchPh')" @input="debounced">
          </div>
        </label>
        <button v-if="hasFilters" class="btn btn-ghost btn-sm" type="button" @click="clearFilters">
          <AppIcon name="close" :size="15" />
          {{ $t('history.clearFilters') }}
        </button>
      </div>
      <div class="filter-groups">
        <div class="filter-group">
          <span>{{ $t('history.status') }}</span>
          <div class="filter-options">
            <button
              v-for="status in statusFilters"
              :key="status.v"
              class="chip"
              :class="{ active: filters.status === status.v }"
              type="button"
              @click="setStatus(status.v)"
            >
              {{ $t(status.l) }}
              <small v-if="counts[status.v] != null">{{ counts[status.v] }}</small>
            </button>
          </div>
        </div>
        <div class="filter-group">
          <span>{{ $t('history.source') }}</span>
          <div class="filter-options">
            <button
              v-for="source in sourceFilters"
              :key="source.v"
              class="chip"
              :class="{ active: filters.source_type === source.v }"
              type="button"
              @click="setSource(source.v)"
            >
              {{ $t(source.l) }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <div v-if="selected.length" class="selection-bar surface">
      <div>
        <span class="selection-icon"><AppIcon name="check-circle" :size="19" weight="fill" /></span>
        <strong>{{ $t('history.selectedCount', { count: selected.length }) }}</strong>
      </div>
      <div class="selection-actions">
        <button class="btn btn-sm" type="button" @click="selected = []">{{ $t('history.clearSelection') }}</button>
        <button class="btn btn-sm" type="button" @click="batchRerun"><AppIcon name="arrow-clockwise" :size="15" />{{ $t('history.batchRerun') }}</button>
        <button class="btn btn-primary btn-sm" type="button" @click="batchExport"><AppIcon name="download" :size="15" />{{ $t('history.batchExport') }}</button>
      </div>
    </div>

    <LoadingState v-if="loading" :label="$t('browser.loading')" :rows="7" />
    <EmptyState
      v-else-if="error"
      class="surface"
      :title="$t('browser.loadError')"
      :description="error"
      icon="warning"
      tone="danger"
    >
      <template #actions>
        <button class="btn btn-sm" type="button" @click="reload"><AppIcon name="arrow-clockwise" :size="15" />{{ $t('browser.retry') }}</button>
      </template>
    </EmptyState>
    <EmptyState
      v-else-if="!items.length"
      class="surface"
      :title="$t('history.noTasks')"
      :description="hasFilters ? $t('history.noFilteredTasks') : $t('history.noTasksHint')"
      icon="clock-history"
    >
      <template #actions>
        <button v-if="hasFilters" class="btn" type="button" @click="clearFilters">{{ $t('history.clearFilters') }}</button>
        <router-link v-else class="btn btn-primary" to="/">{{ $t('history.createTask') }}</router-link>
      </template>
    </EmptyState>

    <template v-else>
      <div class="history-table surface">
        <table class="table">
          <thead>
            <tr>
              <th class="select-column">
                <input type="checkbox" :checked="allChecked" :aria-label="$t('history.selectPage')" @change="toggleAll($event.target.checked)">
              </th>
              <th>{{ $t('history.thSource') }}</th>
              <th>{{ $t('history.thStatus') }}</th>
              <th>{{ $t('history.thTime') }}</th>
              <th>{{ $t('history.thProduct') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="task in items" :key="task.id" :class="{ selected: selected.includes(task.id) }">
              <td class="select-column"><input v-model="selected" type="checkbox" :value="task.id" :aria-label="$t('history.selectTask', { title: displayName(task) })"></td>
              <td>
                <router-link class="task-source" :to="`/task/${task.id}`">
                  <span class="source-type-icon"><AppIcon :name="sourceIcon(task.source_type)" :size="17" weight="duotone" /></span>
                  <span>
                    <strong>{{ displayName(task) }}</strong>
                    <small>{{ task.source_type || '-' }}</small>
                  </span>
                </router-link>
              </td>
              <td><span class="badge" :class="task.status"><span class="d"></span>{{ statusText(task.status) }}</span></td>
              <td class="mono-sm muted">{{ formatDate(task.created_at) }}</td>
              <td>
                <div class="td-actions">
                  <router-link v-if="task.status === 'completed'" class="btn btn-sm" :to="`/note/${task.id}`">{{ $t('common.note') }}</router-link>
                  <router-link v-if="task.status === 'completed'" class="btn btn-sm" :to="`/mindmap/${task.id}`">{{ $t('common.mindmap') }}</router-link>
                  <button v-if="task.status === 'failed'" class="btn btn-sm" type="button" @click="rerun(task.id)"><AppIcon name="arrow-clockwise" :size="14" />{{ $t('history.rerun') }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="history-cards">
        <article v-for="task in items" :key="task.id" class="history-card surface" :class="{ selected: selected.includes(task.id) }">
          <div class="history-card-head">
            <input v-model="selected" type="checkbox" :value="task.id" :aria-label="$t('history.selectTask', { title: displayName(task) })">
            <span class="source-type-icon"><AppIcon :name="sourceIcon(task.source_type)" :size="18" weight="duotone" /></span>
            <router-link :to="`/task/${task.id}`">{{ displayName(task) }}</router-link>
          </div>
          <div class="history-card-meta">
            <span class="badge" :class="task.status"><span class="d"></span>{{ statusText(task.status) }}</span>
            <span>{{ task.source_type || '-' }}</span>
            <span>{{ formatDate(task.created_at) }}</span>
          </div>
          <div class="history-card-actions">
            <router-link v-if="task.status === 'completed'" class="btn btn-sm" :to="`/note/${task.id}`">{{ $t('common.note') }}</router-link>
            <router-link v-if="task.status === 'completed'" class="btn btn-sm" :to="`/mindmap/${task.id}`">{{ $t('common.mindmap') }}</router-link>
            <button v-if="task.status === 'failed'" class="btn btn-sm" type="button" @click="rerun(task.id)"><AppIcon name="arrow-clockwise" :size="14" />{{ $t('history.rerun') }}</button>
          </div>
        </article>
      </div>

      <footer class="pagination">
        <span>{{ $t('history.showing', { start: rangeStart, end: rangeEnd, total }) }}</span>
        <div>
          <button class="btn btn-sm" type="button" :disabled="page <= 1" @click="goPage(page - 1)">{{ $t('history.prev') }}</button>
          <span>{{ page }} / {{ totalPages }}</span>
          <button class="btn btn-sm" type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">{{ $t('history.next') }}</button>
        </div>
      </footer>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import PageHeader from '@/components/PageHeader.vue'
import { batchTasks, listTasks, rerunTask } from '@/api'
import { displayName } from '@/format'
import { i18n } from '@/i18n'

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const q = ref('')
const selected = ref([])
const counts = reactive({})
const filters = reactive({ status: '', source_type: '' })
const loading = ref(true)
const error = ref('')
const statusFilters = [
  { v: '', l: 'history.all' },
  { v: 'running', l: 'status.running' },
  { v: 'completed', l: 'status.completed' },
  { v: 'failed', l: 'status.failed' },
]
const sourceFilters = [
  { v: '', l: 'history.all' },
  { v: 'youtube', l: 'source.youtube' },
  { v: 'bilibili', l: 'source.bilibili' },
  { v: 'direct', l: 'history.direct' },
  { v: 'local_video', l: 'history.localVideo' },
  { v: 'local_audio', l: 'history.localAudio' },
]

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const rangeStart = computed(() => total.value ? (page.value - 1) * pageSize + 1 : 0)
const rangeEnd = computed(() => Math.min(page.value * pageSize, total.value))
const allChecked = computed(() => items.value.length > 0 && items.value.every(task => selected.value.includes(task.id)))
const hasFilters = computed(() => Boolean(q.value || filters.status || filters.source_type))
const statusText = status => i18n.global.t(`status.${status}`)
const formatDate = date => date ? String(date).replace('T', ' ').slice(0, 16) : '-'
let debounceTimer

function sourceIcon(sourceType) {
  if (sourceType === 'local_audio') return 'file-audio'
  if (sourceType === 'local_video') return 'file-video'
  return 'link'
}
function debounced() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    page.value = 1
    reload()
  }, 300)
}
function setStatus(value) {
  filters.status = filters.status === value ? '' : value
  page.value = 1
  reload()
}
function setSource(value) {
  filters.source_type = filters.source_type === value ? '' : value
  page.value = 1
  reload()
}
function clearFilters() {
  q.value = ''
  filters.status = ''
  filters.source_type = ''
  page.value = 1
  reload()
}
function toggleAll(checked) {
  selected.value = checked ? items.value.map(task => task.id) : []
}
function goPage(nextPage) {
  page.value = nextPage
  selected.value = []
  reload()
}
async function reload() {
  loading.value = true
  error.value = ''
  try {
    const response = await listTasks({
      q: q.value || undefined,
      status: filters.status || undefined,
      source_type: filters.source_type || undefined,
      page: page.value,
      page_size: pageSize,
    })
    items.value = response.items || []
    total.value = response.total || 0
    selected.value = selected.value.filter(id => items.value.some(task => task.id === id))
  } catch (loadError) {
    error.value = loadError.message
  } finally {
    loading.value = false
  }
}
async function loadCounts() {
  await Promise.all(statusFilters.filter(status => status.v).map(async status => {
    try {
      const response = await listTasks({ status: status.v, page: 1, page_size: 1 })
      counts[status.v] = response.total
    } catch {
      counts[status.v] = null
    }
  }))
}
async function batchExport() {
  try {
    const response = await fetch('/api/v1/tasks/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_ids: selected.value, action: 'export' }),
    })
    if (!response.ok) throw new Error(`${i18n.global.t('history.exportFail')} ${response.status}`)
    const blob = await response.blob()
    const anchor = document.createElement('a')
    anchor.href = URL.createObjectURL(blob)
    anchor.download = 'vid2note-export.zip'
    anchor.click()
    selected.value = []
  } catch (exportError) {
    alert(exportError.message)
  }
}
async function batchRerun() {
  try {
    await batchTasks(selected.value, 'rerun')
    alert(i18n.global.t('history.batchRerunDone'))
    selected.value = []
    reload()
  } catch (rerunError) {
    alert(rerunError.message)
  }
}
async function rerun(id) {
  try {
    await rerunTask(id)
    reload()
  } catch (rerunError) {
    alert(rerunError.message)
  }
}

onMounted(() => {
  reload()
  loadCounts()
})
onUnmounted(() => clearTimeout(debounceTimer))
</script>

<style scoped>
.history-summary{display:flex;align-items:center;gap:7px;margin-top:9px}
.history-summary span{padding:3px 8px;border:1px solid var(--border);border-radius:999px;background:var(--card);color:var(--muted);font-family:var(--mono);font-size:10px}
.filter-panel{margin-bottom:12px;padding:15px 16px}
.filter-search{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;padding-bottom:13px;border-bottom:1px solid var(--border)}
.filter-search label{display:flex;align-items:center;gap:12px;min-width:0;flex:1}
.filter-search label>span,.filter-group>span{flex:none;color:var(--muted);font-size:11px;font-weight:650}
.filter-search .search{width:min(360px,100%)}
.filter-groups{display:flex;flex-direction:column;gap:10px;padding-top:13px}
.filter-group{display:grid;grid-template-columns:58px minmax(0,1fr);align-items:start;gap:10px}
.filter-group>span{padding-top:6px}
.filter-options{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.filter-options .chip small{margin-left:3px;color:inherit;font-family:var(--mono);font-size:9.5px;opacity:.75}
.selection-bar{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px;padding:10px 12px;border-color:rgba(40,100,220,.22);background:var(--accent-soft)}
.selection-bar>div,.selection-actions{display:flex;align-items:center;gap:8px}
.selection-bar strong{font-size:12px;color:var(--accent)}
.selection-icon{display:grid;place-items:center;color:var(--accent)}
.history-table{overflow:hidden}
.history-table .table th,.history-table .table td{padding-top:12px;padding-bottom:12px}
.history-table tbody tr.selected{background:var(--accent-soft)}
.select-column{width:44px!important;padding-left:16px!important;padding-right:6px!important}
.task-source{display:flex;align-items:center;gap:9px;min-width:0;color:var(--text)}
.source-type-icon{display:grid;place-items:center;width:32px;height:32px;flex:none;border-radius:9px;background:var(--card-2);color:var(--accent)}
.task-source>span:last-child{min-width:0}
.task-source strong,.task-source small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.task-source strong{max-width:480px;font-size:12.5px;font-weight:600}
.task-source small{margin-top:2px;color:var(--muted);font-family:var(--mono);font-size:9.5px}
.history-cards{display:none}
.pagination{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 2px}
.pagination>span{color:var(--muted);font-family:var(--mono);font-size:10.5px}
.pagination>div{display:flex;align-items:center;gap:8px}.pagination>div>span{min-width:42px;color:var(--muted);font-family:var(--mono);font-size:10.5px;text-align:center}

@media (max-width:899px){
  .history-table{display:none}
  .history-cards{display:grid;gap:9px}
  .history-card{padding:13px 14px}
  .history-card.selected{border-color:var(--accent);background:var(--accent-soft)}
  .history-card-head{display:grid;grid-template-columns:18px 34px minmax(0,1fr);align-items:center;gap:8px}
  .history-card-head>a{overflow:hidden;color:var(--text);font-size:12.5px;font-weight:600;text-overflow:ellipsis;white-space:nowrap}
  .history-card-meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:10px 0 10px 60px;color:var(--muted);font-family:var(--mono);font-size:9.5px}
  .history-card-actions{display:flex;align-items:center;gap:7px;margin-left:60px}
}
@media (max-width:767px){
  .filter-search{align-items:stretch;flex-direction:column}
  .filter-search label{align-items:stretch;flex-direction:column;gap:6px}
  .filter-search .search{width:100%}
  .filter-group{grid-template-columns:1fr;gap:4px}
  .selection-bar{align-items:flex-start;flex-direction:column}
  .selection-actions{width:100%;overflow-x:auto}
  .pagination{align-items:flex-start;flex-direction:column}
  .history-card-meta,.history-card-actions{margin-left:0}
}
</style>
