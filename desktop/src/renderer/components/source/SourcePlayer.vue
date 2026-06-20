<template>
  <div class="source-player">
    <video v-if="src" ref="player" controls :src="src" @timeupdate="timeupdate" @seeked="$emit('seeked')" />
    <div v-else class="media-unavailable"><strong>仅字幕证据</strong><p>原始媒体不可用，仍可核对时间化转录。</p><button type="button" @click="$emit('reacquire')">重新获取来源</button></div>
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
const props = withDefaults(defineProps<{ src?: string; startMs: number; endMs: number; mediaOffsetMs?: number }>(), { mediaOffsetMs: 0 })
const emit = defineEmits<{ seeked: []; time: [milliseconds: number]; reacquire: [] }>()
const player = ref<HTMLVideoElement | null>(null)
function seek(): void { if (player.value) player.value.currentTime = Math.max(0, props.startMs - props.mediaOffsetMs) / 1000 }
function timeupdate(): void { const current = (player.value?.currentTime ?? 0) * 1000 + props.mediaOffsetMs; emit('time', current); if (current >= props.endMs) player.value?.pause() }
watch(
  [() => props.src, () => props.startMs, () => props.mediaOffsetMs],
  seek,
  { flush: 'post' },
)
onMounted(seek)
</script>
