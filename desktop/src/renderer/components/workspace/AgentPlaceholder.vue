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
    <div class="agent-runtime">
      <span>Built-in Runtime</span>
      <b>A · 审批</b>
    </div>
    <div class="agent-empty">
      <ChatDotRound />
      <strong>面板已就绪</strong>
      <p>Agent 会话将在运行时接入后显示；所有 Wiki 写回都须经过 ChangeSet。</p>
    </div>
    <form class="agent-composer" @submit.prevent>
      <label class="sr-only" for="agent-draft">询问知识库</label>
      <textarea id="agent-draft" rows="3" placeholder="询问当前知识库…" disabled />
      <button type="submit" disabled>发送</button>
    </form>
  </aside>
</template>

<script setup lang="ts">
import { ChatDotRound, Close } from '@element-plus/icons-vue'

import ResizablePane from './ResizablePane.vue'

defineProps<{ open: boolean; width: number; drawer: boolean }>()
defineEmits<{ close: []; resize: [width: number] }>()
</script>
