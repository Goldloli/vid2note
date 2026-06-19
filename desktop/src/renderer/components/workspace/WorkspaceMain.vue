<template>
  <main class="workspace-main" data-testid="workspace-main" tabindex="-1">
    <header class="workspace-toolbar">
      <button type="button" aria-label="切换文件树" @click="store.toggleTree"><Expand /></button>
      <div class="workspace-breadcrumb"><span>vid2note</span><b>{{ title }}</b></div>
      <span class="autonomy-badge">{{ store.autonomyLabel }}</span>
      <button type="button" aria-label="切换 Agent 面板" @click="store.toggleAgent"><ChatDotRound /></button>
    </header>
    <div class="workspace-scroll"><RouterView /></div>
  </main>
</template>

<script setup lang="ts">
import { ChatDotRound, Expand } from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useWorkspaceStore } from '../../stores/workspace'

const route = useRoute()
const store = useWorkspaceStore()
const title = computed(() => String(route.meta.title ?? '工作台'))
</script>
