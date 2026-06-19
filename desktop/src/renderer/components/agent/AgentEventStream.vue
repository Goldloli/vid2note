<template>
  <ol class="agent-events" aria-live="polite">
    <li v-for="event in events" :key="`${event.run_id}-${event.sequence}`" data-agent-event :data-event-type="event.type">
      <small>{{ labels[event.type] ?? event.type }}</small>
      <p>{{ text(event.payload) }}</p>
      <RouterLink v-if="event.type === 'changeset.proposed' && event.payload.changeset_id" :to="`/workspace/changesets/${event.payload.changeset_id}`">审阅变更</RouterLink>
    </li>
  </ol>
</template>
<script setup lang="ts">
import type { AgentEvent } from '../../api/agents'
defineProps<{ events: readonly AgentEvent[] }>()
const labels: Record<string, string> = { 'run.started': '开始', 'thinking.delta': '思考', 'message.delta': '回答', 'tool.started': '工具开始', 'tool.completed': '工具完成', 'changeset.proposed': '变更建议', 'approval.required': '需要审批', usage: '用量', 'run.completed': '完成', 'run.failed': '失败', 'run.cancelled': '已取消' }
function text(payload: Record<string, unknown>): string {
  for (const key of ['text', 'message', 'summary', 'name', 'code']) if (typeof payload[key] === 'string') return payload[key] as string
  return Object.keys(payload).length ? JSON.stringify(payload) : ''
}
</script>
