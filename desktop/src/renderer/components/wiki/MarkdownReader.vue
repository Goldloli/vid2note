<template><article class="markdown-reader" @click="activate" v-html="html" /></template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from './renderMarkdown'

const props = defineProps<{ content: string }>()
const emit = defineEmits<{
  navigate: [path: string]
  evidence: [reference: { sourceId: string; startMs: number; endMs: number; preview: boolean }]
}>()
const html = computed(() => renderMarkdown(props.content))

function activate(event: MouseEvent): void {
  const anchor = (event.target as HTMLElement).closest('a')
  if (!anchor) return
  const path = anchor.dataset.vaultPath
  const sourceId = anchor.dataset.evidenceSource
  const external = anchor.dataset.externalLink
  if (path || sourceId || external) event.preventDefault()
  if (path) emit('navigate', path)
  if (sourceId) emit('evidence', {
    sourceId,
    startMs: Number(anchor.dataset.startMs),
    endMs: Number(anchor.dataset.endMs),
    preview: event.metaKey || event.ctrlKey,
  })
  if (external && /^https?:\/\//.test(anchor.href)) void window.electronAPI?.openExternal(anchor.href)
}
</script>
