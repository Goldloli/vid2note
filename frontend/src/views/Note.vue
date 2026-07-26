<template>
  <div class="page">
    <div class="spread" style="margin-bottom:16px">
      <strong>{{ $t('note.title') }}</strong>
      <div class="row gap-s">
        <button class="btn btn-sm" @click="copy">{{ $t('note.copyMd') }}</button>
        <a class="btn btn-sm" :href="noteUrl" download>{{ $t('note.exportMd') }}</a>
        <router-link class="btn btn-sm" :to="`/mindmap/${id}`">{{ $t('note.mindmap') }}</router-link>
        <template v-if="taskLoaded">
          <button v-if="hasPdf" class="chip" :class="{active: pdfOn}" @click="pdfOn=!pdfOn">{{ $t('note.pdfToggle') }}</button>
          <span v-else class="muted mono-sm">{{ $t('note.noPdf') }}</span>
        </template>
      </div>
    </div>
    <div :class="['note-layout', { dual: pdfOn }]">
      <aside v-if="toc.length && !pdfOn" class="note-toc card">
        <div class="kicker" style="margin-bottom:10px">{{ $t('note.outline') }}</div>
        <a v-for="t in toc" :key="t.id" :class="['toc-item', `toc-l${t.level}`, { active: activeId === t.id }]" @click="scrollTo(t.id)">{{ t.text }}</a>
      </aside>
      <div class="note-wrap" :class="{ dual: pdfOn }"><div class="note-md" ref="mdRef" v-html="html"></div></div>
      <div v-if="pdfOn && hasPdf" class="note-pdf card"><iframe :src="pdfUrl" class="pdf-frame" :title="$t('note.pdfToggle')"></iframe></div>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import { getProductUrl, getTask } from '@/api'
import { i18n } from '@/i18n'
const id = useRoute().params.id
const html = ref(''); const mdRef = ref(null); const toc = ref([]); const activeId = ref('')
const task = ref({}); const taskLoaded = ref(false); const pdfOn = ref(false)
const noteUrl = getProductUrl(id, 'note')
const pdfUrl = computed(() => getProductUrl(id, 'pdf'))
const hasPdf = computed(() => !!task.value?.pdf_path)
let mdText = ''; let io = null
async function fetchMd() { const res = await fetch(noteUrl); return await res.text() }
async function loadTask() { try { task.value = await getTask(id) } catch(e){} finally { taskLoaded.value = true } }
async function load() {
  try { mdText = await fetchMd(); html.value = marked.parse(mdText); await nextTick(); buildToc() }
  catch(e) { html.value = '<p>' + i18n.global.t('common.loadFail') + ': ' + e.message + '</p>' }
}
function buildToc() {
  const wrap = mdRef.value; if (!wrap) return
  const heads = wrap.querySelectorAll('h1,h2,h3'); const items = []
  heads.forEach((h, i) => { const hid = `nh-${i}`; h.id = hid; items.push({ id: hid, level: Number(h.tagName[1]), text: h.textContent.trim() }) })
  toc.value = items
  if (io) { io.disconnect(); io = null }
  if (items.length) {
    io = new IntersectionObserver((entries) => {
      const vis = entries.filter(e => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      if (vis[0]) activeId.value = vis[0].target.id
    }, { rootMargin: '0px 0px -70% 0px', threshold: 0 })
    items.forEach(t => { const el = document.getElementById(t.id); if (el) io.observe(el) })
  }
}
function scrollTo(hid) { const el = document.getElementById(hid); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); activeId.value = hid }
async function copy() { try { navigator.clipboard.writeText(mdText || await fetchMd()); alert(i18n.global.t('common.copied')) } catch(e){ alert(e.message) } }
onMounted(() => { loadTask(); load() })
onUnmounted(() => io && io.disconnect())
</script>
<style scoped>
.note-layout { display: flex; gap: 18px; align-items: flex-start; }
.note-toc { width: 220px; flex: none; position: sticky; top: 16px; max-height: calc(100vh - 120px); overflow: auto; display: flex; flex-direction: column; gap: 2px; }
.toc-item { font-size: 13px; color: var(--text-2); cursor: pointer; padding: 4px 8px; border-radius: 6px; border-left: 2px solid transparent; transition: .2s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.toc-l2 { padding-left: 20px; } .toc-l3 { padding-left: 32px; font-size: 12px; }
.toc-item:hover { background: var(--card-2); color: var(--text); }
.toc-item.active { color: var(--accent); border-left-color: var(--accent); background: var(--accent-soft); }
.note-wrap { flex: 1; min-width: 0; } .note-wrap.dual { flex: 1; }
.note-pdf { flex: 1; min-width: 0; padding: 0; overflow: hidden; height: calc(100vh - 140px); }
.pdf-frame { width: 100%; height: 100%; border: 0; display: block; }
</style>
