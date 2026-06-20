<template>
  <section class="markdown-editor">
    <div ref="host" aria-label="Markdown 源码" />
    <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
    <footer><button type="button" @click="$emit('cancel')">取消</button><button type="button" @click="save">保存</button></footer>
  </section>
</template>

<script setup lang="ts">
import { markdown } from '@codemirror/lang-markdown'
import { EditorState } from '@codemirror/state'
import { EditorView, keymap } from '@codemirror/view'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ content: string; errorMessage?: string }>()
const emit = defineEmits<{ save: [content: string]; cancel: [] }>()
const host = ref<HTMLElement>()
let editor: EditorView | undefined

function save(): void { if (editor) emit('save', editor.state.doc.toString()) }
function setContent(content: string): void {
  if (!editor || editor.state.doc.toString() === content) return
  editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: content } })
}

onMounted(() => {
  editor = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.content,
      extensions: [
        markdown(),
        EditorView.lineWrapping,
        keymap.of([
          { key: 'Mod-s', run: () => { save(); return true } },
          { key: 'Escape', run: () => { emit('cancel'); return true } },
        ]),
      ],
    }),
  })
  editor.focus()
})
watch(() => props.content, setContent)
onBeforeUnmount(() => editor?.destroy())
defineExpose({ setContent })
</script>
