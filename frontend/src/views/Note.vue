<template>
  <div class="page page-wide note-detail">
    <PageHeader :title="task.title || $t('note.title')" :subtitle="$t('note.detailSubtitle')" icon="notes">
      <template #actions>
        <button class="btn" type="button" @click="copy"><AppIcon name="copy" :size="16" />{{ $t('note.copyMd') }}</button>
        <a class="btn" :href="noteUrl" download><AppIcon name="download" :size="16" />{{ $t('note.exportMd') }}</a>
        <button class="btn" type="button" @click="exportPdf"><AppIcon name="file-pdf" :size="16" />{{ $t('note.exportPdf') }}</button>
        <router-link class="btn btn-primary" :to="`/mindmap/${id}`"><AppIcon name="mindmap" :size="16" />{{ $t('note.mindmap') }}</router-link>
      </template>
      <template #meta>
        <div v-if="taskLoaded" class="note-meta">
          <span>{{ task.asr_engine || '-' }}</span>
          <span>{{ task.llm_provider || task.llm_model || '-' }}</span>
          <button v-if="hasPdf" class="text-action" type="button" :aria-pressed="pdfOn" @click="pdfOn = !pdfOn">
            <AppIcon name="file-pdf" :size="14" />
            {{ pdfOn ? $t('note.hidePdf') : $t('note.pdfToggle') }}
          </button>
          <span v-else>{{ $t('note.noPdf') }}</span>
        </div>
      </template>
    </PageHeader>

    <div class="note-layout" :class="{ dual: pdfOn }">
      <aside v-if="toc.length && !pdfOn" class="note-toc surface">
        <div class="toc-head"><AppIcon name="book-open" :size="16" />{{ $t('note.outline') }}</div>
        <nav>
          <button
            v-for="heading in toc"
            :key="heading.id"
            class="toc-item"
            :class="[`toc-l${heading.level}`, { active: activeId === heading.id }]"
            type="button"
            @click="scrollTo(heading.id)"
          >
            {{ heading.text }}
          </button>
        </nav>
      </aside>

      <main class="note-paper surface">
        <LoadingState v-if="loading" class="note-loading" :label="$t('browser.loading')" :rows="8" />
        <EmptyState
          v-else-if="error"
          class="note-state"
          :title="$t('browser.loadError')"
          :description="error"
          icon="warning"
          tone="danger"
        >
          <template #actions>
            <button class="btn btn-sm" type="button" @click="load"><AppIcon name="arrow-clockwise" :size="15" />{{ $t('browser.retry') }}</button>
          </template>
        </EmptyState>
        <article
          v-else
          class="note-md"
          ref="mdRef"
          v-html="html"
          @error.capture="handleImageError"
        ></article>
      </main>

      <section v-if="pdfOn && hasPdf" class="note-pdf surface">
        <div class="pdf-head">
          <span><AppIcon name="file-pdf" :size="16" />{{ $t('note.pdfDocument') }}</span>
          <button class="icon-btn" type="button" :aria-label="$t('note.hidePdf')" @click="pdfOn = false"><AppIcon name="close" :size="16" /></button>
        </div>
        <iframe :src="pdfUrl" class="pdf-frame" :title="$t('note.pdfToggle')"></iframe>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingState from '@/components/LoadingState.vue'
import PageHeader from '@/components/PageHeader.vue'
import { getProductUrl, getTask } from '@/api'
import { noteImageError, readProductText, rewriteTaskScreenshotLinks } from '@/artifacts'
import { i18n } from '@/i18n'
import { renderMarkdown } from '@/markdown'

const id = useRoute().params.id
const html = ref('')
const mdRef = ref(null)
const toc = ref([])
const activeId = ref('')
const task = ref({})
const taskLoaded = ref(false)
const pdfOn = ref(false)
const loading = ref(true)
const error = ref('')
const noteUrl = getProductUrl(id, 'note')
const pdfUrl = computed(() => getProductUrl(id, 'pdf'))
const hasPdf = computed(() => Boolean(task.value?.pdf_path))
let markdownText = ''
let observer

async function fetchMarkdown() {
  const result = await readProductText({
    url: noteUrl,
    available: Boolean(task.value?.note_path),
  })
  if (result.state !== 'ready') throw new Error(i18n.global.t('note.productUnavailable'))
  return result.text
}
async function loadTask() {
  task.value = await getTask(id)
  taskLoaded.value = true
}
async function load() {
  loading.value = true
  error.value = ''
  clearToc()
  try {
    await loadTask()
    markdownText = await fetchMarkdown()
    html.value = renderMarkdown(
      rewriteTaskScreenshotLinks(
        markdownText,
        id,
        task.value?.screenshot_paths || [],
      ),
    )
    loading.value = false
    await nextTick()
    buildToc()
  } catch (loadError) {
    html.value = ''
    clearToc()
    error.value = loadError.message
  } finally {
    loading.value = false
  }
}
function handleImageError(event) {
  noteImageError(event, i18n.global.t('note.imageUnavailable'))
}
function clearToc() {
  if (observer) {
    observer.disconnect()
    observer = null
  }
  toc.value = []
  activeId.value = ''
}
function buildToc() {
  clearToc()
  const wrap = mdRef.value
  if (!wrap) return
  const headings = Array.from(wrap.querySelectorAll('h2,h3,h4')).map((heading, index) => {
    const headingId = `note-heading-${index}`
    heading.id = headingId
    return { id: headingId, level: Number(heading.tagName[1]), text: heading.textContent.trim() }
  })
  toc.value = headings
  observer = new IntersectionObserver(entries => {
    const visible = entries.filter(entry => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
    if (visible[0]) activeId.value = visible[0].target.id
  }, { rootMargin: '0px 0px -70% 0px', threshold: 0 })
  headings.forEach(heading => {
    const element = wrap.querySelector(`#${heading.id}`)
    if (element) observer.observe(element)
  })
}
function scrollTo(headingId) {
  const element = mdRef.value?.querySelector(`#${headingId}`)
  if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  activeId.value = headingId
}
async function copy() {
  try {
    await navigator.clipboard.writeText(markdownText || await fetchMarkdown())
    alert(i18n.global.t('common.copied'))
  } catch (copyError) {
    alert(copyError.message)
  }
}
async function exportPdf() {
  try {
    const html2pdf = (await import('html2pdf.js')).default
    html2pdf().set({
      margin: 10,
      filename: `${task.value?.title || 'note'}.pdf`,
      html2canvas: { scale: 2 },
      jsPDF: { unit: 'mm', format: 'a4' },
    }).from(mdRef.value).save()
  } catch (exportError) {
    alert(exportError.message)
  }
}

onMounted(load)
onUnmounted(() => {
  if (observer) observer.disconnect()
})
</script>

<style scoped>
.note-meta{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:9px}
.note-meta>span,.text-action{display:inline-flex;align-items:center;gap:5px;min-height:24px;padding:2px 8px;border:1px solid var(--border);border-radius:999px;background:var(--card);color:var(--muted);font-family:var(--mono);font-size:10px}
.text-action{color:var(--accent);font-family:var(--font);cursor:pointer}
.note-layout{display:grid;grid-template-columns:220px minmax(0,1fr);align-items:start;gap:14px}
.note-layout.dual{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.note-toc{position:sticky;top:0;max-height:calc(100dvh - 150px);overflow:auto;padding:10px}
.toc-head{display:flex;align-items:center;gap:7px;padding:7px 8px 10px;color:var(--muted);font-size:11px;font-weight:650}
.note-toc nav{display:flex;flex-direction:column;gap:2px}
.toc-item{width:100%;padding:6px 8px;border-left:2px solid transparent;border-radius:var(--r-sm);color:var(--text-2);font-size:12px;text-align:left}
.toc-item:hover{background:var(--card-2);color:var(--text)}
.toc-item.active{border-left-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.toc-l2{padding-left:8px}.toc-l3{padding-left:20px}.toc-l4{padding-left:32px;font-size:11px}
.note-paper{min-width:0;padding:38px 48px 68px}
.note-paper .note-md{max-width:760px;margin:0 auto}
.note-loading{border:0;box-shadow:none}
.note-state{min-height:420px}
.note-pdf{display:flex;min-width:0;height:calc(100dvh - 158px);flex-direction:column;overflow:hidden}
.pdf-head{display:flex;align-items:center;justify-content:space-between;min-height:48px;padding:6px 10px 6px 14px;border-bottom:1px solid var(--border)}
.pdf-head span{display:flex;align-items:center;gap:7px;color:var(--text-2);font-size:12px;font-weight:600}
.pdf-frame{display:block;width:100%;height:100%;border:0;background:var(--card-2)}

@media (max-width:1050px){
  .note-layout{grid-template-columns:190px minmax(0,1fr)}
  .note-paper{padding:32px 36px 58px}
}
@media (max-width:899px){
  .note-layout,.note-layout.dual{grid-template-columns:1fr}
  .note-toc{position:relative;max-height:240px}
  .note-paper{padding:30px 32px 54px}
  .note-pdf{height:70dvh;min-height:520px}
}
@media (max-width:767px){
  .note-paper{padding:24px 18px 46px}
}
</style>
