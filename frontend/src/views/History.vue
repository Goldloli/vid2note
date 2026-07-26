<template>
  <div class="page">
    <div class="spread" style="margin-bottom:14px">
      <strong>{{ $t('history.title') }}</strong>
      <input class="input" style="max-width:280px" v-model="q" :placeholder="$t('history.searchPh')" @input="debounced">
    </div>
    <div class="row gap-s wrap" style="margin-bottom:12px">
      <span class="kicker">{{ $t('history.status') }}</span>
      <button v-for="s in statusFilters" :key="s.v" class="chip btn-sm" :class="{active: filters.status===s.v}" @click="setStatus(s.v)">
        {{ $t(s.l) }}<span class="muted mono-sm" v-if="counts[s.v]!=null"> ·{{ counts[s.v] }}</span>
      </button>
      <span class="kicker" style="margin-left:12px">{{ $t('history.source') }}</span>
      <button v-for="s in sourceFilters" :key="s.v" class="chip btn-sm" :class="{active: filters.source_type===s.v}" @click="setSource(s.v)">{{ $t(s.l) }}</button>
    </div>
    <div class="card"><table class="table">
      <thead><tr>
        <th style="width:32px"><input type="checkbox" :checked="allChecked" @change="toggleAll($event.target.checked)"></th>
        <th>{{ $t('history.thSource') }}</th><th>{{ $t('history.thStatus') }}</th><th>{{ $t('history.thTime') }}</th><th>{{ $t('history.thProduct') }}</th>
      </tr></thead>
      <tbody>
        <tr v-for="t in items" :key="t.id">
          <td><input type="checkbox" :value="t.id" v-model="selected"></td>
          <td><div class="src-cell">{{ displayName(t) }}</div></td>
          <td><span class="badge" :class="t.status"><span class="d"></span>{{ statusText(t.status) }}</span></td>
          <td class="mono-sm muted">{{ fmt(t.created_at) }}</td>
          <td class="td-actions">
            <router-link class="btn btn-sm" :to="`/note/${t.id}`">{{ $t('common.note') }}</router-link>
            <button v-if="t.status==='failed'" class="btn btn-sm" @click="rerun(t.id)">{{ $t('history.rerun') }}</button>
          </td>
        </tr>
        <tr v-if="!items.length"><td colspan="5" class="muted" style="padding:24px;text-align:center">{{ $t('history.noTasks') }}</td></tr>
      </tbody>
    </table></div>
    <div class="spread" style="margin-top:14px">
      <div class="row gap-s">
        <button class="btn btn-sm" v-if="selected.length" @click="batchExport">{{ $t('history.batchExport') }}({{ selected.length }})</button>
        <button class="btn btn-sm" v-if="selected.length" @click="batchRerun">{{ $t('history.batchRerun') }}</button>
      </div>
      <div class="row gap-s" v-if="total">
        <span class="mono-sm muted">{{ $t('history.showing', { start: rangeStart, end: rangeEnd, total }) }}</span>
        <button class="btn btn-sm" :disabled="page<=1" @click="goPage(page-1)">{{ $t('history.prev') }}</button>
        <button class="btn btn-sm" :disabled="page>=totalPages" @click="goPage(page+1)">{{ $t('history.next') }}</button>
      </div>
    </div>
  </div>
</template>
<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { listTasks, batchTasks, rerunTask } from '@/api'
import { i18n } from '@/i18n'
import { displayName } from '@/format'
const items = ref([]); const total = ref(0); const page = ref(1); const pageSize = 20
const q = ref(''); const selected = ref([]); const counts = reactive({})
const filters = reactive({ status: '', source_type: '' })
const statusFilters = [{v:'',l:'history.all'},{v:'running',l:'status.running'},{v:'completed',l:'status.completed'},{v:'failed',l:'status.failed'}]
const sourceFilters = [{v:'',l:'history.all'},{v:'youtube',l:'YouTube'},{v:'bilibili',l:'Bilibili'},{v:'direct',l:'history.direct'},{v:'local_video',l:'history.localVideo'},{v:'local_audio',l:'history.localAudio'}]
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const rangeStart = computed(() => total.value ? (page.value - 1) * pageSize + 1 : 0)
const rangeEnd = computed(() => Math.min(page.value * pageSize, total.value))
const allChecked = computed(() => items.value.length > 0 && items.value.every(t => selected.value.includes(t.id)))
const statusText = s => i18n.global.t('status.' + s)
const fmt = d => d ? String(d).replace('T', ' ').slice(0, 16) : ''
let dt
function debounced() { clearTimeout(dt); dt = setTimeout(() => { page.value = 1; reload() }, 300) }
function setStatus(v) { filters.status = filters.status === v ? '' : v; page.value = 1; reload() }
function setSource(v) { filters.source_type = filters.source_type === v ? '' : v; page.value = 1; reload() }
function toggleAll(c) { selected.value = c ? items.value.map(t => t.id) : [] }
function goPage(p) { page.value = p; reload() }
async function reload() {
  try {
    const res = await listTasks({ q: q.value || undefined, status: filters.status || undefined, source_type: filters.source_type || undefined, page: page.value, page_size: pageSize })
    items.value = res.items || []; total.value = res.total || 0
  } catch (e) {}
}
async function loadCounts() {
  for (const s of statusFilters) { if (!s.v) continue; try { const r = await listTasks({ status: s.v, page: 1, page_size: 1 }); counts[s.v] = r.total } catch (e) {} }
}
async function batchExport() {
  try {
    const res = await fetch('/api/v1/tasks/batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_ids: selected.value, action: 'export' }) })
    if (!res.ok) throw new Error(i18n.global.t('history.exportFail') + ' ' + res.status)
    const blob = await res.blob()
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'vid2note-export.zip'; a.click()
    selected.value = []
  } catch (e) { alert(e.message) }
}
async function batchRerun() {
  try { await batchTasks(selected.value, 'rerun'); alert(i18n.global.t('history.batchRerunDone')); selected.value = []; reload() } catch (e) { alert(e.message) }
}
async function rerun(id) { try { await rerunTask(id); reload() } catch (e) { alert(e.message) } }
onMounted(() => { reload(); loadCounts() })
</script>
