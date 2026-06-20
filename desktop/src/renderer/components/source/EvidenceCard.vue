<template><article class="evidence-card"><strong>{{ title }}</strong><span>{{ format(reference.start_ms) }}–{{ format(reference.end_ms ?? reference.start_ms) }}</span><p v-if="!reference.playable">仅字幕证据</p><img v-else-if="reference.kind === 'frame' && assetUrl" :src="assetUrl" alt="来源证据截图"></article></template>
<script setup lang="ts">
import type { MediaReference } from '../../api/media'
defineProps<{ reference: MediaReference; title: string; assetUrl?: string }>()
const format = (value: number): string => `${(value / 1000).toFixed(1)}s`
</script>
