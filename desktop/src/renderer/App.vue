<template>
  <div class="app">
    <!-- 标题栏（macOS traffic light 风格）-->
    <div class="titlebar">
      <div class="traffic">
        <span class="t-close"></span><span class="t-min"></span><span class="t-max"></span>
      </div>
      <div class="tb-title"><b>vid2note</b> — {{ pageTitle }}</div>
      <div class="tb-spacer"></div>
      <span class="tb-pill"><span class="dot-live"></span>本地服务 · :8765</span>
      <button class="btn btn-icon btn-sm" @click="toggleTheme" title="切换明暗">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/>
        </svg>
      </button>
    </div>

    <div class="body">
      <!-- 侧栏 -->
      <aside class="sidebar">
        <router-link to="/" class="brand">
          <div class="mark">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 6h16M4 12h10M4 18h7"/><circle cx="18" cy="16" r="3" fill="currentColor" stroke="none"/>
            </svg>
          </div>
          <div>
            <div class="name">vid2note</div>
            <div class="ver">v0.1.0 · electron</div>
          </div>
        </router-link>

        <div class="nav-group">
          <div class="nav-label">工作台</div>
          <router-link to="/" class="nav-item" :class="{active: isHome}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
            主控台
          </router-link>
          <router-link v-if="currentTaskId" :to="`/tasks/${currentTaskId}`" class="nav-item" :class="{active: isTaskDetail}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3.5" cy="6" r="1.4"/><circle cx="3.5" cy="12" r="1.4"/><circle cx="3.5" cy="18" r="1.4"/></svg>
            任务详情
          </router-link>
          <router-link to="/settings" class="nav-item" :class="{active: isSettings}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3.2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/></svg>
            设置
          </router-link>
        </div>

        <div class="sidebar-foot">
          <div class="engine-card">
            <div class="row"><span class="lbl">ASR</span><span class="val">asrtools-b · 云端</span></div>
            <div class="row"><span class="lbl">LLM</span><span class="val">qwen-turbo</span></div>
            <div class="row"><span class="lbl">引擎</span>
              <span class="row gap-xs"><span class="dot-live" style="width:6px;height:6px"></span><span class="val" style="color:var(--success)">Python 运行中</span></span>
            </div>
          </div>
        </div>
      </aside>

      <!-- 内容区 -->
      <main class="content">
        <div class="topbar">
          <div class="crumbs"><b>{{ pageTitle }}</b></div>
        </div>
        <div class="scroll">
          <router-view />
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const currentTaskId = ref(null)

const isHome = computed(() => route.path === '/')
const isTaskDetail = computed(() => route.path.startsWith('/tasks/'))
const isSettings = computed(() => route.path.startsWith('/settings'))

const pageTitle = computed(() => {
  if (isSettings.value) return '设置'
  if (isTaskDetail.value) return '任务详情'
  return '主控台'
})

// 跟踪最近访问的任务 id（供侧栏跳转）
watch(() => route.params.id, (id) => {
  if (id) currentTaskId.value = id
}, { immediate: true })

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme')
  const next = cur === 'dark' ? 'light' : 'dark'
  document.documentElement.setAttribute('data-theme', next)
  try { localStorage.setItem('v2n-theme', next) } catch (e) { /* ignore */ }
}

onMounted(() => {
  // 恢复已保存主题
  try {
    const saved = localStorage.getItem('v2n-theme')
    if (saved) document.documentElement.setAttribute('data-theme', saved)
  } catch (e) { /* ignore */ }
})
</script>

<style scoped>
</style>
