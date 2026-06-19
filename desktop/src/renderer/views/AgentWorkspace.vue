<template><section class="focus-workspace agent-workspace"><header class="focus-header"><div><small>隔离运行时</small><h1>Agent 会话</h1></div></header><div class="review-grid"><nav class="changeset-list" aria-label="历史 Agent 会话"><h2>会话</h2><button v-for="session in store.sessions" :key="session.id" type="button" @click="store.resume(session)"><strong>{{ session.runtime_id }}</strong><small>{{ session.status }} · {{ new Date(session.updated_at).toLocaleString() }}</small></button></nav><AgentPanel /></div></section></template>
<script setup lang="ts">
import { onMounted } from 'vue'
import AgentPanel from '../components/agent/AgentPanel.vue'
import { useAgentStore } from '../stores/agent'
const store = useAgentStore()
onMounted(store.refreshSessions)
</script>
