<template>
  <div class="app">
    <!-- 标题栏：macOS 原生 traffic light 由系统绘制，这里只放标题与右侧按钮 -->
    <div class="titlebar">
      <div class="tb-title"><b>vid2note</b> — {{ pageTitle }}</div>
      <div class="tb-spacer"></div>
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
          <router-link to="/history" class="nav-item" :class="{active: isHistory}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
            历史
          </router-link>
          <router-link v-if="currentTaskId" :to="`/note/${currentTaskId}`" class="nav-item" :class="{active: isNote}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 3v4a1 1 0 001 1h4"/><path d="M5 3h9l5 5v11a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2z"/><line x1="8" y1="13" x2="14" y2="13"/><line x1="8" y1="17" x2="14" y2="17"/></svg>
            笔记
          </router-link>
          <router-link v-if="currentTaskId" :to="`/mindmap/${currentTaskId}`" class="nav-item" :class="{active: isMindmap}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v3M12 10l-5 7M12 10l5 7"/></svg>
            思维导图
          </router-link>
          <router-link to="/settings" class="nav-item" :class="{active: isSettings}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3.2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/></svg>
            设置
          </router-link>
        </div>

        <div class="sidebar-foot">
          <div class="engine-card">
            <div class="row"><span class="lbl">ASR</span><span class="val">funasr · 本地</span></div>
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
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useReveal } from './composables/useReveal'

const route = useRoute()
const router = useRouter()
useReveal(router)
const currentTaskId = ref(null)

const isHome = computed(() => route.path === '/')
const isHistory = computed(() => route.path.startsWith('/history'))
const isTaskDetail = computed(() => route.path.startsWith('/tasks/'))
const isNote = computed(() => route.path.startsWith('/note/'))
const isMindmap = computed(() => route.path.startsWith('/mindmap/'))
const isSettings = computed(() => route.path.startsWith('/settings'))

const pageTitle = computed(() => {
  if (isSettings.value) return '设置'
  if (isHistory.value) return '历史'
  if (isTaskDetail.value) return '任务详情'
  if (isNote.value) return '笔记'
  if (isMindmap.value) return '思维导图'
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
