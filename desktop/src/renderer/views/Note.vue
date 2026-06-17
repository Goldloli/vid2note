<template>
  <div class="page">
    <div class="spread" style="margin-bottom:20px">
      <div class="page-head" style="margin:0"><h1>笔记预览</h1><div class="sub mono-sm">{{ id }}</div></div>
      <div class="row gap-s">
        <button class="btn btn-sm" @click="copy">复制</button>
        <button class="btn btn-sm" @click="exportMd">导出 .md</button>
        <router-link v-if="id" :to="`/tasks/${id}`" class="btn btn-sm">任务详情</router-link>
      </div>
    </div>

    <div class="note-grid">
      <!-- 大纲 -->
      <aside class="note-side card card-pad" v-if="headings.length">
        <div class="kicker" style="margin-bottom:10px">大纲</div>
        <a v-for="h in headings" :key="h.id" class="outline-item" :class="'o-depth-'+h.depth" @click="scrollTo(h.id)">{{ h.text }}</a>
      </aside>
      <!-- 正文 -->
      <div class="card card-pad">
        <div v-if="loading" class="muted">加载中…</div>
        <div v-else-if="!markdown" class="muted">暂无笔记。任务可能尚未完成。</div>
        <div v-else class="note-md" v-html="rendered"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getProcessResult } from '../api/process'

const route = useRoute()
const id = computed(() => route.params.id || '')
const markdown = ref('')
const loading = ref(true)

// 极简 markdown 渲染（避免引入 marked 依赖）
const rendered = computed(() => renderMd(markdown.value))
const headings = computed(() => {
  const lines = markdown.value.split('\n')
  const result = []
  for (const line of lines) {
    const m = line.match(/^(#{1,4})\s+(.+)/)
    if (m) result.push({ depth: m[1].length, text: m[2], id: slug(m[2]) })
  }
  return result
})

function renderMd(md) {
  if (!md) return ''
  let html = md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^### (.+)$/gm, '<h3 id="$1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 id="$1">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 id="$1">$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.+<\/li>\n?)+/g, (m) => '<ul>' + m + '</ul>')
    .replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>')
    .replace(/\n\n/g, '</p><p>')
  return '<p>' + html + '</p>'
}
function slug(t) { return t.replace(/\s+/g, '-').toLowerCase() }
function scrollTo(id) { const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }) }

async function copy() { try { await navigator.clipboard.writeText(markdown.value) } catch (e) {} }
function exportMd() { const blob = new Blob([markdown.value], { type: 'text/markdown' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `note-${id.value}.md`; a.click() }

onMounted(async () => {
  try {
    const res = await getProcessResult(id.value)
    markdown.value = res.artifacts?.markdown || ''
  } catch (e) { /* 任务未完成 */ }
  loading.value = false
})
</script>

<style scoped>
.note-grid { display:grid; grid-template-columns: 220px 1fr; gap:20px; align-items:start; }
.note-side { position:sticky; top:18px; }
.outline-item { display:block; padding:4px 0; font-size:12.5px; color:var(--muted); cursor:pointer; transition:color var(--t-fast) var(--ease); }
.outline-item:hover { color:var(--accent); }
.o-depth-1 { font-weight:600; color:var(--fg); }
.o-depth-2 { padding-left:12px; }
.o-depth-3 { padding-left:24px; }
@media (max-width: 800px) { .note-grid { grid-template-columns: 1fr; } .note-side { display:none; } }
</style>
