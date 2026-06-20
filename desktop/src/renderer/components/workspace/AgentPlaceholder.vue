<template>
  <aside
    class="agent-panel"
    data-testid="agent-panel"
    aria-label="Agent 面板"
    :aria-hidden="!open"
    :class="{ 'is-hidden': !open }"
    :style="{ width: `${width}px` }"
  >
    <ResizablePane
      v-if="!drawer"
      :model-value="width"
      :min="320"
      :max="560"
      side="left"
      label="调整 Agent 面板宽度"
      @update:model-value="$emit('resize', $event)"
    />
    <header class="agent-heading">
      <div><span class="agent-kicker">Agent</span><strong>知识助手</strong></div>
      <button type="button" aria-label="关闭 Agent 面板" @click="$emit('close')"><Close /></button>
    </header>
    <div class="agent-runtime"><span>知识运行时</span><b>{{ autonomyLabel }}</b></div>
    <AgentPanel />
  </aside>
</template>

<script setup lang="ts">
import { Close } from '@element-plus/icons-vue'

import AgentPanel from '../agent/AgentPanel.vue'
import ResizablePane from './ResizablePane.vue'

defineProps<{ open: boolean; width: number; drawer: boolean; autonomyLabel: string }>()
defineEmits<{ close: []; resize: [width: number] }>()
</script>
