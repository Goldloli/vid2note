<template>
  <div class="pipeline-rail">
    <template v-for="(n, i) in nodes" :key="n.key">
      <div class="pr-node" :class="n.status"><div class="pr-dot"></div><div class="pr-label">{{ $t(n.labelKey) }}</div></div>
      <div v-if="i < nodes.length-1" class="pr-link" :class="{done: n.status==='completed'}"><i></i></div>
    </template>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ nodes: { type: Object, default: () => ({}) } })
const order = [['download','pipeline.download'],['extract_audio','pipeline.audio'],['asr','pipeline.asr'],['note','pipeline.note'],['mindmap','pipeline.mindmap'],['cleanup','pipeline.cleanup']]
const nodes = computed(() => order.map(([k, labelKey]) => ({ key: k, labelKey, status: (props.nodes[k] && props.nodes[k].status) || 'pending' })))
</script>
