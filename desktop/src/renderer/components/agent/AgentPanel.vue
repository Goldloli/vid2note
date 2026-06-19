<template><div class="agent-conversation"><RuntimePicker v-model="store.selectedRuntime" :runtimes="store.runtimes" :locked="store.running" /><p class="autonomy-copy">{{ workspace.autonomyMode === 'approval' ? '审批模式：所有 Wiki 写回均进入 ChangeSet。' : '自治策略由工作台设置统一控制。' }}</p><button v-if="vault.currentPage && !contextPaths.includes(vault.currentPage.path)" class="attach-current" type="button" @click="contextPaths.push(vault.currentPage.path)">附加当前页：{{ vault.currentPage.path }}</button><p v-if="store.lastError" role="alert">{{ store.lastError.code }} · {{ store.lastError.message }}</p><AgentEventStream :events="store.events" /><div v-if="!store.events.length" class="agent-empty"><ChatDotRound /><strong>基于 Markdown Vault 回答</strong><p>只发送你明确附加的页面；外部 CLI 在隔离工作区运行。</p></div><AgentComposer :running="store.running" :context-paths="contextPaths" @send="store.send($event, contextPaths)" @cancel="store.cancel" @remove-context="remove" /></div></template>
<script setup lang="ts">
import { ChatDotRound } from '@element-plus/icons-vue'; import { onMounted, ref } from 'vue'
import { useAgentStore } from '../../stores/agent'; import { useWorkspaceStore } from '../../stores/workspace'; import AgentComposer from './AgentComposer.vue'; import AgentEventStream from './AgentEventStream.vue'; import RuntimePicker from './RuntimePicker.vue'
import { useVaultStore } from '../../stores/vault'
const store = useAgentStore(); const workspace = useWorkspaceStore(); const contextPaths = ref<string[]>([])
const vault = useVaultStore()
function remove(path: string): void { contextPaths.value = contextPaths.value.filter((item) => item !== path) }
onMounted(store.refreshRuntimes)
</script>
