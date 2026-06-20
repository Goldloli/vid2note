<template>
  <div ref="viewport" class="source-timeline" role="region" aria-label="转录时间线" @scroll="onScroll">
    <ol class="source-timeline-list" :style="{ height: `${segments.length * ROW_HEIGHT}px` }">
      <li v-for="item in visible" :key="item.segment.id" :style="{ transform: `translateY(${item.index * ROW_HEIGHT}px)`, height: `${ROW_HEIGHT}px` }"><button type="button" :data-segment-id="item.segment.id" :aria-current="activeId === item.segment.id ? 'true' : undefined" @click="$emit('seek', item.segment)"><time>{{ format(item.segment.startMs) }}</time><span>{{ item.segment.text }}</span></button></li>
    </ol>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
export type TranscriptSegment = { id: string; startMs: number; endMs: number; text: string }
const props = defineProps<{ segments: TranscriptSegment[]; activeId?: string }>()
defineEmits<{ seek: [segment: TranscriptSegment] }>()
const ROW_HEIGHT = 52
const WINDOW_SIZE = 48
const viewport = ref<HTMLElement>()
const scrollTop = ref(0)
const visible = computed(() => {
  const start = Math.max(0, Math.floor(scrollTop.value / ROW_HEIGHT) - 8)
  return props.segments.slice(start, start + WINDOW_SIZE).map((segment, offset) => ({ segment, index: start + offset }))
})
function onScroll(event: Event): void { scrollTop.value = (event.currentTarget as HTMLElement).scrollTop }
watch(() => props.activeId, async (activeId) => {
  if (!activeId) return
  const index = props.segments.findIndex((segment) => segment.id === activeId)
  if (index < 0) return
  const first = Math.floor(scrollTop.value / ROW_HEIGHT)
  if (index >= first && index < first + WINDOW_SIZE - 8) return
  scrollTop.value = Math.max(0, (index - 12) * ROW_HEIGHT)
  await nextTick()
  if (viewport.value) viewport.value.scrollTop = scrollTop.value
}, { immediate: true })
const format = (value: number): string => `${Math.floor(value / 60000)}:${String(Math.floor(value / 1000) % 60).padStart(2, '0')}`
</script>
