<template>
  <div class="page">
    <div class="spread" style="margin-bottom:20px">
      <div class="page-head" style="margin:0"><h1>思维导图</h1><div class="sub mono-sm">{{ id }}</div></div>
      <div class="row gap-s">
        <button class="btn btn-sm" @click="copy">复制源码</button>
        <button class="btn btn-sm" @click="exportMmd">导出 .mmd</button>
        <router-link v-if="id" :to="`/tasks/${id}`" class="btn btn-sm">任务详情</router-link>
      </div>
    </div>

    <div class="mm-grid">
      <!-- Mermaid 渲染区 -->
      <div class="card card-pad mm-canvas">
        <div v-if="loading" class="muted">加载中…</div>
        <div v-else-if="!mermaidText" class="muted">暂无思维导图。任务可能尚未完成。</div>
        <div v-else class="mm-render" v-html="renderedSvg"></div>
      </div>
      <!-- 文本大纲 -->
      <aside class="card card-pad mm-side">
        <div class="kicker" style="margin-bottom:10px">源码</div>
        <pre class="mm-src">{{ mermaidText }}</pre>
        <div class="divider-h" style="margin:12px 0"></div>
        <div class="kicker" style="margin-bottom:8px">大纲</div>
        <div v-for="(line, i) in outline" :key="i" class="mm-outline" :class="'d-'+line.depth">{{ line.text }}</div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getProcessResult } from '../api/process'

const route = useRoute()
const id = computed(() => route.params.id || '')
const mermaidText = ref('')
const renderedSvg = ref('')
const loading = ref(true)

const outline = computed(() => {
  if (!mermaidText.value) return []
  const lines = mermaidText.value.split('\n')
  const result = []
  for (const line of lines) {
    const m = line.match(/^(\s*)(.+)$/)
    if (m && m[2].trim() && !m[2].trim().startsWith('mindmap')) {
      result.push({ depth: Math.min(4, Math.floor(m[1].length / 2) + 1), text: m[2].trim().replace(/\(.*?\)|\[.*?\]|\{.*?\}/g, '') })
    }
  }
  return result
})

function escapeHtml(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') }

async function renderMermaid() {
  if (!mermaidText.value) return
  // mermaid 未加载（离线 / CDN 失败）时回退为源码显示
  if (typeof window === 'undefined' || !window.mermaid) {
    renderedSvg.value = `<div class="mm-fallback"><pre>${escapeHtml(mermaidText.value)}</pre></div>`
    return
  }
  try {
    // mermaid v10+ 返回 Promise，不再用 callback；每次用唯一 id 避免重渲染冲突
    const { svg } = await window.mermaid.render('mm-svg-' + Date.now(), mermaidText.value)
    renderedSvg.value = svg
  } catch (e) {
    // 语法错误或渲染失败时降级显示源码
    renderedSvg.value = `<div class="mm-fallback"><pre>${escapeHtml(mermaidText.value)}</pre></div>`
  }
}

async function copy() { try { await navigator.clipboard.writeText(mermaidText.value) } catch (e) {} }
function exportMmd() { const blob = new Blob([mermaidText.value], { type: 'text/plain' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `mindmap-${id.value}.mmd`; a.click() }

onMounted(async () => {
  try {
    const res = await getProcessResult(id.value)
    mermaidText.value = res.artifacts?.mindmap || ''
    if (mermaidText.value) await renderMermaid()
  } catch (e) {}
  loading.value = false
})
</script>

<style scoped>
.mm-grid { display:grid; grid-template-columns: 1fr 300px; gap:20px; align-items:start; }
.mm-canvas { min-height:400px; display:grid; place-items:center; }
.mm-render { width:100%; }
.mm-render :deep(svg) { max-width:100%; height:auto; }
.mm-fallback pre { white-space:pre-wrap; font-family:var(--font-mono); font-size:12.5px; }
.mm-src { white-space:pre-wrap; font-family:var(--font-mono); font-size:11.5px; color:var(--muted); max-height:200px; overflow:auto; }
.mm-outline { font-size:12.5px; padding:3px 0; color:var(--muted); }
.mm-outline.d-1 { font-weight:600; color:var(--fg); }
.mm-outline.d-2 { padding-left:12px; }
.mm-outline.d-3 { padding-left:24px; }
.mm-outline.d-4 { padding-left:36px; }
@media (max-width: 800px) { .mm-grid { grid-template-columns: 1fr; } }
</style>
