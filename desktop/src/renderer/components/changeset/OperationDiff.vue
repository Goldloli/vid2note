<template><div ref="host" class="operation-diff" /></template>

<script setup lang="ts">
import { EditorState } from '@codemirror/state'
import { EditorView } from '@codemirror/view'
import { MergeView } from '@codemirror/merge'
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{ before: string; after: string }>()
const host = ref<HTMLElement>()
let merge: MergeView | undefined

onMounted(() => {
  merge = new MergeView({
    parent: host.value,
    a: { doc: props.before, extensions: [EditorState.readOnly.of(true), EditorView.lineWrapping] },
    b: { doc: props.after, extensions: [EditorState.readOnly.of(true), EditorView.lineWrapping] },
    collapseUnchanged: { margin: 3, minSize: 4 },
  })
})
onBeforeUnmount(() => merge?.destroy())
</script>
