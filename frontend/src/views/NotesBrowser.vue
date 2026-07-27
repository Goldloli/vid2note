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
    <main class="br-mid"><div class="note-md" ref="mdRef" v-html="html"></div></main>
    <aside class="br-right card">
      <div class="br-tabs">
        <button class="chip btn-sm" :class="{active:tab==='outline'}" @click="tab='outline'">{{ $t('note.outline') }}</button>
        <button class="chip btn-sm" :class="{active:tab==='action'}" @click="tab='action'">{{ $t('browser.action') }}</button>
      </div>
      <div v-if="tab==='outline'" class="br-tab-body">
        <a v-for="t in toc" :key="t.id" :class="['toc-item',`toc-l${t.level}`]" @click="scrollTo(t.id)">{{ t.text }}</a>
        <div v-if="!toc.length" class="muted mono-sm">—</div>
      </div>
      <div v-else class="br-tab-body">
        <a class="btn btn-sm block" :href="noteUrl" download>{{ $t('note.exportMd') }}</a>
        <button class="btn btn-sm block" @click="copy">{{ $t('note.copyMd') }}</button>
        <button class="btn btn-sm block" @click="exportPdf">{{ $t('note.exportPdf') }}</button>
        <router-link class="btn btn-sm block" :to="`/mindmaps?id=${selectedId}`">{{ $t('note.mindmap') }}</router-link>
        <div class="muted mono-sm meta" v-if="task">
          <div>{{ $t('task.metaAsr') }}: {{ task.asr_engine }}</div>
          <div>{{ $t('task.metaLlm') }}: {{ task.llm_provider }}/{{ task.llm_model }}</div>
          <div>{{ $t('task.metaSource') }}: {{ task.source_url }}</div>
        </div>
      </div>
    </aside>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import { listTasks, getTask, getProductUrl } from '@/api'
import { i18n } from '@/i18n'
import { displayName } from '@/format'
const route = useRoute()
const items = ref([]); const q = ref(''); const selectedId = ref(''); const task = ref(null)
const html = ref(''); const mdRef = ref(null); const toc = ref([]); const tab = ref('outline')
const noteUrl = computed(() => selectedId.value ? getProductUrl(selectedId.value, 'note') : '')
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
  selectedId.value = id; tab.value = 'outline'
  try { task.value = await getTask(id) } catch (e) { task.value = null }
  try {
    const res = await fetch(getProductUrl(id, 'note')); const md = await res.text()
    html.value = marked.parse(md); await nextTick(); buildToc()
  } catch (e) { html.value = '<p>' + i18n.global.t('common.loadFail') + '</p>'; toc.value = [] }
}
function buildToc() {
  const wrap = mdRef.value; if (!wrap) return
  const heads = wrap.querySelectorAll('h1,h2,h3'); const arr = []
  heads.forEach((h, i) => { const hid = `nh-${i}`; h.id = hid; arr.push({ id: hid, level: Number(h.tagName[1]), text: h.textContent.trim() }) })
  toc.value = arr
}
function scrollTo(hid) { const el = document.getElementById(hid); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
async function copy() { try { const res = await fetch(noteUrl.value); navigator.clipboard.writeText(await res.text()); alert(i18n.global.t('common.copied')) } catch (e) { alert(e.message) } }
async function exportPdf() {
  try {
    const html2pdf = (await import('html2pdf.js')).default
    html2pdf().set({ margin: 10, filename: (task.value?.title || 'note') + '.pdf', html2canvas: { scale: 2 }, jsPDF: { unit: 'mm', format: 'a4' } }).from(mdRef.value).save()
  } catch(e) { alert(e.message) }
}
onMounted(() => { const id = route.query.id; reload().then(() => { if (id) select(String(id)) }) })
onUnmounted(() => clearTimeout(dt))
</script>
<style scoped>
.browser { display: flex; gap: 14px; height: calc(100vh - 90px); }
.br-left { width: 240px; flex: none; display: flex; flex-direction: column; }
.br-list { flex: 1; overflow: auto; }
.br-item { display: block; padding: 10px; border-radius: 6px; cursor: pointer; border-left: 2px solid transparent; }
.br-item:hover { background: var(--card-2); }
.br-item.active { background: var(--accent-soft); border-left-color: var(--accent); }
.br-item-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.br-mid { flex: 1; min-width: 0; overflow: auto; padding: 0 8px; }
.br-mid .note-md { max-width: 720px; margin: 0 auto; }
.br-right { width: 280px; flex: none; display: flex; flex-direction: column; }
.br-tabs { display: flex; gap: 6px; margin-bottom: 10px; }
.br-tab-body { flex: 1; overflow: auto; }
.toc-item { display: block; font-size: 13px; color: var(--text-2); cursor: pointer; padding: 4px 8px; border-radius: 6px; border-left: 2px solid transparent; }
.toc-l2 { padding-left: 20px; } .toc-l3 { padding-left: 32px; font-size: 12px; }
.toc-item:hover { background: var(--card-2); }
.block { display: block; width: 100%; margin-bottom: 6px; box-sizing: border-box; text-align: center; }
.meta { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
</style>
