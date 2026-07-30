<template>
  <div class="page-workspace notes-library">
    <PageHeader :title="$t('note.libraryTitle')" :subtitle="$t('note.librarySubtitle')" icon="notes">
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
          {{ $t('note.outline') }}
        </button>
      </template>
    </PageHeader>

    <div class="library-workspace" :class="{ 'library-visible': libraryOpen, 'context-visible': contextOpen }">
      <LibrarySidebar
        v-model:query="q"
        :title="$t('note.libraryList')"
        :items="items"
        :selected-id="selectedId"
        :loading="listLoading"
        :error="listError"
        item-icon="notes"
        :search-placeholder="$t('history.searchPh')"
        :loading-label="$t('browser.loading')"
        :empty-title="$t('note.emptyLibrary')"
        :empty-description="$t('note.emptyLibraryHint')"
        :error-title="$t('browser.loadError')"
        :retry-label="$t('browser.retry')"
        @update:query="debounced"
        @select="select"
        @retry="reload"
      />

      <main class="reader-panel surface">
        <template v-if="selectedId">
          <div class="reader-toolbar">
            <div class="reader-heading">
              <strong>{{ task ? displayName(task) : $t('note.title') }}</strong>
              <small v-if="task">{{ task.asr_engine || '-' }} / {{ task.llm_provider || task.llm_model || '-' }}</small>
            </div>
            <div class="reader-actions">
              <button class="icon-btn" type="button" :title="$t('note.copyMd')" :aria-label="$t('note.copyMd')" @click="copy">
                <AppIcon name="copy" :size="17" />
              </button>
              <a class="icon-btn" :href="noteUrl" download :title="$t('note.exportMd')" :aria-label="$t('note.exportMd')">
                <AppIcon name="download" :size="17" />
              </a>
              <button class="icon-btn" type="button" :title="$t('note.exportPdf')" :aria-label="$t('note.exportPdf')" @click="exportPdf">
                <AppIcon name="file-pdf" :size="17" />
              </button>
            </div>
          </div>
          <LoadingState v-if="contentLoading" class="reader-loading" :label="$t('browser.loading')" :rows="7" />
          <EmptyState
            v-else-if="contentError"
            class="reader-state"
            :title="$t('browser.loadError')"
            :description="contentError"
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
          <div v-else class="reader-scroll">
            <article
              class="note-md"
              ref="mdRef"
              v-html="html"
              @error.capture="handleImageError"
            ></article>
          </div>
        </template>
        <EmptyState
          v-else
          class="reader-state"
          :title="$t('note.selectTitle')"
          :description="$t('note.selectHint')"
          icon="book-open"
        />
      </main>

      <aside class="context-panel surface">
        <div class="context-tabs">
          <button :class="{ active: tab === 'outline' }" type="button" @click="tab = 'outline'">{{ $t('note.outline') }}</button>
          <button :class="{ active: tab === 'action' }" type="button" @click="tab = 'action'">{{ $t('browser.action') }}</button>
        </div>
        <div v-if="tab === 'outline'" class="context-body toc-list">
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
          <EmptyState
            v-if="!toc.length"
            class="context-empty"
            :title="$t('note.noOutline')"
            :description="$t('note.noOutlineHint')"
            icon="book-open"
          />
        </div>
        <div v-else class="context-body action-stack">
          <a class="btn" :href="noteUrl" download><AppIcon name="download" :size="16" />{{ $t('note.exportMd') }}</a>
          <button class="btn" type="button" @click="copy"><AppIcon name="copy" :size="16" />{{ $t('note.copyMd') }}</button>
          <button class="btn" type="button" @click="exportPdf"><AppIcon name="file-pdf" :size="16" />{{ $t('note.exportPdf') }}</button>
          <router-link class="btn btn-primary" :to="`/mindmaps?id=${selectedId}`"><AppIcon name="mindmap" :size="16" />{{ $t('note.mindmap') }}</router-link>
          <dl v-if="task" class="artifact-meta">
            <div><dt>{{ $t('task.metaAsr') }}</dt><dd>{{ task.asr_engine || '-' }}</dd></div>
            <div><dt>{{ $t('task.metaLlm') }}</dt><dd>{{ task.llm_provider || '-' }}</dd></div>
            <div><dt>{{ $t('task.metaSource') }}</dt><dd>{{ task.source_type || '-' }}</dd></div>
          </dl>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import EmptyState from '@/components/EmptyState.vue'
import LibrarySidebar from '@/components/LibrarySidebar.vue'
import LoadingState from '@/components/LoadingState.vue'
import PageHeader from '@/components/PageHeader.vue'
import { getProductUrl, getTask, listTasks } from '@/api'
import { noteImageError, readProductText, rewriteTaskScreenshotLinks } from '@/artifacts'
import { displayName } from '@/format'
import { i18n } from '@/i18n'
import { renderMarkdown } from '@/markdown'

const route = useRoute()
const router = useRouter()
const items = ref([])
const q = ref('')
const selectedId = ref('')
const task = ref(null)
const html = ref('')
const mdRef = ref(null)
const toc = ref([])
const tab = ref('outline')
const activeId = ref('')
const listLoading = ref(true)
const listError = ref('')
const contentLoading = ref(false)
const contentError = ref('')
const libraryOpen = ref(false)
const contextOpen = ref(false)
const noteUrl = computed(() => selectedId.value ? getProductUrl(selectedId.value, 'note') : '')
let debounceTimer
let observer
let markdownText = ''

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
      html.value = ''
      toc.value = []
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
  contentLoading.value = true
  contentError.value = ''
  clearToc()
  router.replace({ query: { ...route.query, id: nextId } }).catch(() => {})
  try {
    const taskResponse = await getTask(nextId)
    const noteResponse = await readProductText({
      url: getProductUrl(nextId, 'note'),
      available: Boolean(taskResponse?.note_path),
    })
    if (noteResponse.state !== 'ready') {
      throw new Error(i18n.global.t('note.productUnavailable'))
    }
    task.value = taskResponse
    markdownText = noteResponse.text
    html.value = renderMarkdown(
      rewriteTaskScreenshotLinks(
        markdownText,
        nextId,
        taskResponse?.screenshot_paths || [],
      ),
    )
    contentLoading.value = false
    await nextTick()
    buildToc()
  } catch (error) {
    task.value = null
    html.value = ''
    clearToc()
    contentError.value = error.message
  } finally {
    contentLoading.value = false
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
    const id = `library-note-heading-${index}`
    heading.id = id
    return { id, level: Number(heading.tagName[1]), text: heading.textContent.trim() }
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
function scrollTo(id) {
  const element = mdRef.value?.querySelector(`#${id}`)
  if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  activeId.value = id
}
async function copy() {
  try {
    if (!markdownText && noteUrl.value) {
      const response = await fetch(noteUrl.value)
      markdownText = await response.text()
    }
    await navigator.clipboard.writeText(markdownText)
    alert(i18n.global.t('common.copied'))
  } catch (error) {
    alert(error.message)
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
  } catch (error) {
    alert(error.message)
  }
}

onMounted(reload)
onUnmounted(() => {
  clearTimeout(debounceTimer)
  if (observer) observer.disconnect()
})
</script>

<style scoped>
.library-workspace{position:relative;display:grid;grid-template-columns:minmax(220px,250px) minmax(0,1fr) minmax(250px,280px);gap:12px;height:calc(100dvh - 170px);min-height:560px}
.reader-panel,.context-panel{display:flex;min-width:0;min-height:0;flex-direction:column;overflow:hidden}
.reader-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:57px;padding:10px 14px;border-bottom:1px solid var(--border);background:var(--card)}
.reader-heading{min-width:0}.reader-heading strong,.reader-heading small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.reader-heading strong{font-size:12.5px}.reader-heading small{margin-top:2px;color:var(--muted);font-family:var(--mono);font-size:9.5px}
.reader-actions{display:flex;align-items:center;gap:3px}
.reader-scroll{flex:1;min-height:0;overflow:auto;padding:34px 42px 64px}
.reader-scroll .note-md{max-width:760px;margin:0 auto}
.reader-loading{margin:18px;border:0;box-shadow:none}
.reader-state{flex:1}
.context-tabs{display:grid;grid-template-columns:1fr 1fr;padding:7px;border-bottom:1px solid var(--border);background:var(--card)}
.context-tabs button{height:32px;border-radius:var(--r-sm);color:var(--muted);font-size:12px;font-weight:600}
.context-tabs button:hover{background:var(--card-2);color:var(--text)}
.context-tabs button.active{background:var(--accent-soft);color:var(--accent)}
.context-body{flex:1;min-height:0;overflow:auto;padding:12px}
.toc-list{display:flex;flex-direction:column;gap:2px}
.toc-item{width:100%;padding:6px 8px;border-left:2px solid transparent;border-radius:var(--r-sm);color:var(--text-2);font-size:12px;text-align:left}
.toc-item:hover{background:var(--card-2);color:var(--text)}
.toc-item.active{border-left-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.toc-l2{padding-left:8px}.toc-l3{padding-left:20px}.toc-l4{padding-left:32px;font-size:11px}
.context-empty{min-height:260px;padding:18px}
.action-stack{display:flex;flex-direction:column;gap:7px}
.artifact-meta{margin-top:7px;padding:5px 10px;border:1px solid var(--border);border-radius:var(--r);background:var(--card-2)}
.artifact-meta div{padding:7px 0;border-bottom:1px solid var(--border)}.artifact-meta div:last-child{border-bottom:0}
.artifact-meta dt{color:var(--muted);font-size:10px}.artifact-meta dd{margin-top:2px;overflow:hidden;color:var(--text-2);font-family:var(--mono);font-size:10.5px;text-overflow:ellipsis}
.workspace-toggle{display:none}

@media (max-width:1179px){
  .library-workspace{grid-template-columns:240px minmax(0,1fr)}
  .context-panel{display:none}
  .context-visible .reader-panel{display:none}
  .context-visible .context-panel{display:flex;grid-column:2}
  .toggle-context{display:inline-flex}
}
@media (max-width:899px){
  .library-workspace{grid-template-columns:1fr;height:auto;min-height:620px}
  .library-workspace :deep(.library-sidebar){display:none;height:420px}
  .library-visible :deep(.library-sidebar){display:flex}
  .library-visible .reader-panel,.library-visible .context-panel{display:none}
  .context-visible .context-panel{display:flex;grid-column:1;min-height:620px}
  .context-visible .reader-panel{display:none}
  .toggle-library{display:inline-flex}
  .reader-panel{min-height:620px}
  .reader-scroll{padding:28px 30px 54px}
}
@media (max-width:767px){
  .reader-scroll{padding:24px 18px 48px}
}
</style>
