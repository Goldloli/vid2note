<template>
  <div>
    <div role="tree" aria-label="Vault 文件">
      <button v-for="(node, index) in nodes" :key="node.path" role="treeitem" class="tree-item" :class="{ 'is-active': node.path === activePath }"
        :data-path="node.path" :aria-expanded="node.directory ? expanded.has(node.path) : undefined" :tabindex="index === focusIndex ? 0 : -1"
        @click="activate(node)" @keydown="onKeydown($event, index)">
        <Folder v-if="node.directory" /><Document v-else /> <span>{{ node.label }}</span><small v-if="node.status">{{ node.status }}</small>
      </button>
    </div>
    <button data-testid="pending-count" type="button" class="tree-status" @click="$emit('review')"><span>待审批</span><b>{{ pendingCount }}</b></button>
  </div>
</template>
<script setup lang="ts">
import { Document, Folder } from '@element-plus/icons-vue'
import { computed, nextTick, ref } from 'vue'
import type { VaultTreeEntry } from '../../api/vault'
const props = defineProps<{ tree: VaultTreeEntry[]; pendingCount: number; activePath?: string }>()
const emit = defineEmits<{ open: [path: string]; review: [] }>()
type Node = { path: string; label: string; directory: boolean; status?: string }
const expanded = ref(new Set(['wiki', 'sources']))
const focusIndex = ref(0)
const nodes = computed<Node[]>(() => {
  const directories = new Set(props.tree.map((entry) => entry.path.split('/')[0]).filter((part) => props.tree.some((entry) => entry.path.startsWith(`${part}/`))))
  const priority = ['index.md', 'wiki', 'sources', 'raw', 'log.md']
  const result: Node[] = []
  for (const path of priority) {
    if (directories.has(path)) result.push({ path, label: path, directory: true })
    const direct = props.tree.find((entry) => entry.path === path)
    if (direct) result.push({ path, label: direct.name, directory: false })
    if (directories.has(path) && expanded.value.has(path)) {
      result.push(...props.tree.filter((entry) => entry.path.startsWith(`${path}/`)).map((entry) => ({ path: entry.path, label: `  ${entry.name}`, directory: false })))
    }
  }
  for (const entry of props.tree) if (!result.some((node) => node.path === entry.path)) result.push({ path: entry.path, label: entry.name, directory: false })
  return result
})
function activate(node: Node): void {
  if (node.directory) { const next = new Set(expanded.value); next.has(node.path) ? next.delete(node.path) : next.add(node.path); expanded.value = next }
  else emit('open', node.path)
}
function onKeydown(event: KeyboardEvent, index: number): void {
  const container = (event.currentTarget as HTMLElement).parentElement
  const node = nodes.value[index]
  if (event.key === 'ArrowDown') focusIndex.value = Math.min(nodes.value.length - 1, index + 1)
  else if (event.key === 'ArrowUp') focusIndex.value = Math.max(0, index - 1)
  else if (event.key === 'Enter') activate(node!)
  else if (event.key === 'ArrowRight' && node?.directory) {
    if (!expanded.value.has(node.path)) { const next = new Set(expanded.value); next.add(node.path); expanded.value = next }
    else focusIndex.value = Math.min(nodes.value.length - 1, index + 1)
  }
  else if (event.key === 'ArrowLeft') {
    if (node?.directory && expanded.value.has(node.path)) { const next = new Set(expanded.value); next.delete(node.path); expanded.value = next }
    else if (node) { const parentIndex = nodes.value.findIndex((candidate) => candidate.directory && node.path.startsWith(`${candidate.path}/`)); if (parentIndex >= 0) focusIndex.value = parentIndex }
  }
  else return
  event.preventDefault(); void nextTick(() => container?.querySelectorAll<HTMLElement>('[role="treeitem"]')[focusIndex.value]?.focus())
}
</script>
