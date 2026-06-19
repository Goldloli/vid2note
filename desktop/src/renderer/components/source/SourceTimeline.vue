<template>
  <ol class="source-timeline" aria-label="转录时间线">
    <li v-for="segment in segments" :key="segment.id"><button type="button" :data-segment-id="segment.id" :aria-current="activeId === segment.id ? 'true' : undefined" @click="$emit('seek', segment)"><time>{{ format(segment.startMs) }}</time><span>{{ segment.text }}</span></button></li>
  </ol>
</template>
<script setup lang="ts">
export type TranscriptSegment = { id: string; startMs: number; endMs: number; text: string }
defineProps<{ segments: TranscriptSegment[]; activeId?: string }>()
defineEmits<{ seek: [segment: TranscriptSegment] }>()
const format = (value: number): string => `${Math.floor(value / 60000)}:${String(Math.floor(value / 1000) % 60).padStart(2, '0')}`
</script>
