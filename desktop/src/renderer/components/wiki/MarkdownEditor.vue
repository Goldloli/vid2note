<template>
  <section class="markdown-editor">
    <label class="sr-only" for="wiki-source">Markdown 源码</label>
    <textarea id="wiki-source" v-model="draft" autofocus @keydown="onKeydown" />
    <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
    <footer><button type="button" @click="$emit('cancel')">取消</button><button type="button" @click="save">保存</button></footer>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
const props = defineProps<{ content: string; errorMessage?: string }>()
const emit = defineEmits<{ save: [content: string]; cancel: [] }>()
const draft = ref(props.content)
watch(() => props.content, (value) => { draft.value = value })
function save(): void { emit('save', draft.value) }
function onKeydown(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save() }
  if (event.key === 'Escape') emit('cancel')
}
</script>
