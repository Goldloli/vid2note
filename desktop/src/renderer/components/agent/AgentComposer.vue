<template><form class="agent-composer" @submit.prevent="submit"><div class="attachment-chips"><button v-for="path in contextPaths" :key="path" type="button" @click="$emit('remove-context', path)">{{ path }} ×</button></div><label class="sr-only" for="agent-draft">询问知识库</label><textarea id="agent-draft" v-model="draft" rows="3" placeholder="询问当前知识库…" @keydown.enter="enter" /><button v-if="running" type="button" @click="$emit('cancel')">停止</button><button v-else type="submit" :disabled="!draft.trim()">发送</button></form></template>
<script setup lang="ts">
import { ref } from 'vue'
defineProps<{ running: boolean; contextPaths: string[] }>(); const emit = defineEmits<{ send: [message: string]; cancel: []; 'remove-context': [path: string] }>(); const draft = ref('')
function submit(): void { const message = draft.value.trim(); if (!message) return; emit('send', message); draft.value = '' }
function enter(event: KeyboardEvent): void { if (!event.shiftKey) { event.preventDefault(); submit() } }
</script>
