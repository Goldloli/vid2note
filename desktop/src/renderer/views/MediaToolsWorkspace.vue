<template><section class="focus-workspace"><header class="focus-header"><div><small>可追溯媒体</small><h1>媒体工具</h1></div></header><form class="card card-pad" @submit.prevent><label>Source ID<input v-model="sourceId" class="input" placeholder="src_20260619_…"></label><label>开始时间（毫秒）<input v-model.number="startMs" class="input" type="number" min="0"></label><label>结束时间（毫秒）<input v-model.number="endMs" class="input" type="number" min="1"></label><div class="row gap-s"><button class="btn" type="button" @click="frame">生成证据截图</button><button class="btn" type="button" @click="clip">生成时间片段</button></div></form><p v-if="media.error" role="alert">媒体生成失败，请检查来源和时间范围。</p><EvidenceCard v-if="media.current" :reference="media.current" title="生成的媒体证据" :asset-url="assetUrl" /><div class="tool-cards"><article v-for="tool in tools" :key="tool.title"><h2>{{ tool.title }}</h2><p>{{ tool.description }}</p><RouterLink :to="tool.to">{{ tool.action }}</RouterLink></article></div><p>截图与片段始终保留 source id 和毫秒时间范围；长任务复用任务队列与实时状态。</p></section></template>
<script setup lang="ts">
import { ref } from 'vue'
import { getBaseURL } from '../api/client'
import EvidenceCard from '../components/source/EvidenceCard.vue'
import { useMediaStore } from '../stores/media'
const media = useMediaStore(); const sourceId = ref(''); const startMs = ref(0); const endMs = ref(30_000); const assetUrl = ref<string>()
async function updateUrl(): Promise<void> { assetUrl.value = media.current ? `${await getBaseURL()}/media/asset?path=${encodeURIComponent(media.current.asset_path)}` : undefined }
async function frame(): Promise<void> { await media.frame(sourceId.value, startMs.value); await updateUrl() }
async function clip(): Promise<void> { await media.clip(sourceId.value, startMs.value, endMs.value); await updateUrl() }
const tools = [
  { title: '转音频', description: '导入视频后由真实 Worker 提取音轨。', to: '/workspace/import', action: '导入视频' },
  { title: '任务与产物', description: '查看媒体长任务、恢复状态和现有产物。', to: '/workspace/history', action: '查看任务' },
  { title: '思维导图', description: '从来源笔记导出结构图。', to: '/workspace/history?view=mindmap', action: '选择来源' },
]
</script>
