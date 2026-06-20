<template><nav class="changeset-list" aria-label="ChangeSet 列表"><section v-for="status in statuses" :key="status"><h2>{{ labels[status] }}</h2><RouterLink v-for="item in items.filter((entry) => entry.status === status)" :key="item.id" :to="`/workspace/changesets/${item.id}`"><strong>{{ item.summary }}</strong><small>{{ item.agent_runtime }} · {{ item.source_ids.join(', ') }}</small><span v-if="item.validation_result?.issues.length">{{ item.validation_result.issues.length }} 项校验</span></RouterLink></section></nav></template>
<script setup lang="ts">
import type { ChangeSet } from '../../api/changesets'
defineProps<{ items: ChangeSet[] }>()
const statuses = ['pending', 'applied', 'rejected', 'reverted'] as const
const labels = { pending: '待审批', applied: '已应用', rejected: '已拒绝', reverted: '已回滚' }
</script>
