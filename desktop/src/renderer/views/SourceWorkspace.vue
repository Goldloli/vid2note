<template>
  <section class="focus-workspace source-workspace">
    <header class="focus-header"><div><small>来源证据 · {{ sourceId }}</small><h1>{{ source?.title ?? '载入来源…' }}</h1></div><RouterLink :to="{ path: '/workspace/wiki', query: { path: `sources/${sourceId}.md` } }">来源笔记</RouterLink></header>
    <p v-if="error" role="alert">{{ error }}</p>
    <div class="source-grid">
      <SourcePlayer :src="clipUrl" :start-ms="range.start" :end-ms="range.end" :media-offset-ms="clip?.rendered_start_ms ?? 0" @time="currentMs = $event" />
      <SourceTimeline :segments="segments" :active-id="active?.id" @seek="seek" />
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getBaseURL } from '../api/client'
import { getClip, type MediaReference } from '../api/media'
import { readSource, readVaultPage, type SourceRecord } from '../api/vault'
import SourcePlayer from '../components/source/SourcePlayer.vue'
import SourceTimeline, { type TranscriptSegment } from '../components/source/SourceTimeline.vue'
import { parseTranscript } from '../components/source/transcript'
const props = defineProps<{ sourceId: string }>(); const route = useRoute(); const source = ref<SourceRecord>(); const segments = ref<TranscriptSegment[]>([]); const clipUrl = ref<string>(); const clip = ref<MediaReference>(); const error = ref(''); const currentMs = ref(0)
const range = reactive({ start: Number(route.query.start ?? 0), end: Number(route.query.end ?? 30000) })
const active = computed(() => segments.value.find((item) => currentMs.value >= item.startMs && currentMs.value < item.endMs))
async function loadClip(): Promise<void> { try { clip.value = await getClip(props.sourceId, range.start, range.end); clipUrl.value = `${await getBaseURL()}/media/asset?path=${encodeURIComponent(clip.value.asset_path)}` } catch { clip.value = undefined; clipUrl.value = undefined } }
function seek(segment: TranscriptSegment): void { range.start = segment.startMs; range.end = segment.endMs; currentMs.value = segment.startMs; void loadClip() }
onMounted(async () => { try { source.value = await readSource(props.sourceId); range.start = Math.min(range.start, Math.max(0, source.value.duration_ms - 1)); range.end = Math.min(Math.max(range.end, range.start + 1), source.value.duration_ms); const page = await readVaultPage(`raw/${props.sourceId}/transcript.md`); segments.value = parseTranscript(page.content); await loadClip() } catch (cause) { error.value = cause instanceof Error ? cause.message : '来源载入失败' } })
</script>
