<template>
  <div class="app">
    <header class="titlebar">
      <div class="tb-title"><b>vid2note</b> — personal knowledge workspace</div>
      <div class="tb-spacer" />
      <button class="btn btn-icon" type="button" aria-label="切换明暗主题" @click="toggleTheme"><Moon /></button>
    </header>
    <WorkspaceLayout />
  </div>
</template>

<script setup lang="ts">
import { Moon } from '@element-plus/icons-vue'
import { onMounted } from 'vue'

import WorkspaceLayout from './layouts/WorkspaceLayout.vue'

const applyTheme = (theme: string): void => document.documentElement.setAttribute('data-theme', theme)

const toggleTheme = (): void => {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'
  applyTheme(next)
  localStorage.setItem('v2n-theme', next)
}

onMounted(() => applyTheme(localStorage.getItem('v2n-theme') || 'light'))
</script>
