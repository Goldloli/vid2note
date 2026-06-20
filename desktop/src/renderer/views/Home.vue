<template>
  <div class="page">
    <header class="page-head">
      <div class="eyebrow">媒体入口</div>
      <h1>导入与处理</h1>
      <p class="sub">将视频链接或本地字幕转为可追溯的来源笔记。</p>
    </header>
    <!-- 输入 composer -->
    <section class="card card-pad reveal" style="margin-bottom:22px">
      <div class="eyebrow" style="margin-bottom:10px">新建任务</div>
      <form class="input-affix" @submit.prevent="submit" style="height:48px">
        <span class="lead">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1"/><path d="M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1"/></svg>
        </span>
        <input class="input" v-model="url" placeholder="粘贴视频链接（YouTube / Bilibili / 直链），回车开始" :disabled="store.isCreating">
        <span class="append">
          <button type="submit" class="btn btn-primary" :disabled="store.isCreating">
            开始
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
        </span>
      </form>
      <p v-if="store.error" class="muted mono-sm" style="margin-top:8px;color:var(--danger)">{{ store.error }}</p>

      <div class="spread" style="margin-top:14px; flex-wrap:wrap; gap:12px">
        <label class="btn btn-sm">
          导入 SRT
          <input
            data-testid="srt-input"
            type="file"
            accept=".srt"
            hidden
            :disabled="store.isCreating"
            @change="importSrt"
          >
        </label>
        <button type="button" class="btn btn-sm" :disabled="store.isCreating || !canChooseLocalVideo" @click="chooseLocalVideo">导入本地视频</button>
        <div class="row gap-s">
          <span class="kicker">ASR</span>
          <button type="button" class="chip active">FunASR 本地</button>
        </div>
        <div class="row gap-s">
          <span class="kicker">LLM</span>
          <button type="button" class="chip active">qwen-turbo</button>
          <button type="button" class="chip">deepseek-chat</button>
          <button type="button" class="chip">ollama · llama3</button>
        </div>
      </div>
      <p class="muted mono-sm" style="margin-top:12px">在线来源由下载器获取；本地视频和 SRT 留在本机。选择云 ASR/LLM 时内容可能发送给对应提供商。请确认你有权处理和保存该来源。</p>
    </section>

    <!-- 统计 -->
    <section class="grid grid-4 reveal" style="margin-bottom:24px">
      <div class="card stat"><div class="row gap-xs"><div class="v">{{ activeCount }}</div><span class="badge running" style="margin-left:auto"><span class="d"></span>进行</span></div><div class="l">进行中任务</div></div>
      <div class="card stat"><div class="v">{{ completedCount }}</div><div class="l">已完成</div></div>
      <div class="card stat"><div class="v">{{ store.tasks.length }}</div><div class="l">累计任务</div></div>
      <div class="card stat"><div class="v">{{ failedCount }}</div><div class="l">失败</div></div>
    </section>

    <!-- 进行中 -->
    <div class="section-title reveal">
      <h2>进行中 <span class="muted mono-sm" style="font-weight:400">· {{ activeCount }}</span></h2>
      <span class="more">实时同步 · SSE</span>
    </div>
    <div v-if="activeTasks.length === 0" class="card card-pad muted reveal" style="margin-bottom:12px;text-align:center">暂无进行中任务，粘贴链接开始。</div>
    <div v-for="task in activeTasks" :key="task.id" class="card card-pad reveal" style="margin-bottom:12px">
      <PipelineRail :progress="task.progress || 0" :status="task.status" :title="taskTitle(task)" :source="task.video_url || task.video_file || ''" :task-id="task.id" />
    </div>

    <!-- 最近完成 -->
    <div v-if="completedTasks.length" class="section-title reveal" style="margin-top:28px">
      <h2>最近完成</h2>
    </div>
    <div v-if="completedTasks.length" class="card reveal" style="overflow:hidden">
      <div class="table">
        <table>
          <thead><tr><th>来源</th><th>状态</th><th>进度</th><th style="text-align:right">产物</th></tr></thead>
          <tbody>
            <tr v-for="task in completedTasks" :key="task.id">
              <td>
                <div class="src-cell">
                  <span class="plat-ico" :class="platClass(task)">{{ platChar(task) }}</span>
                  <div>
                    <div style="font-weight:500">{{ taskTitle(task) }}</div>
                    <div class="muted mono-sm">{{ task.video_url || task.video_file || '—' }}</div>
                  </div>
                </div>
              </td>
              <td><span class="badge completed"><span class="d"></span>已完成</span></td>
              <td class="mono-sm muted">{{ task.progress || 100 }}%</td>
              <td>
                <div class="row gap-xs" style="justify-content:flex-end">
                  <router-link :to="`/workspace/tasks/${task.id}`" class="btn btn-sm">详情</router-link>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTaskStore } from '../stores/task'
import PipelineRail from '../components/PipelineRail.vue'

const store = useTaskStore()
const route = useRoute()
const url = ref(typeof route.query.url === 'string' ? route.query.url : '')
const canChooseLocalVideo = Boolean(window.electronAPI?.chooseLocalVideo)

const activeTasks = computed(() => store.tasks.filter((t) => t.status === 'running' || t.status === 'pending'))
const completedTasks = computed(() => store.tasks.filter((t) => t.status === 'completed').slice(0, 6))
const activeCount = computed(() => activeTasks.value.length)
const completedCount = computed(() => store.tasks.filter((t) => t.status === 'completed').length)
const failedCount = computed(() => store.tasks.filter((t) => t.status === 'failed').length)

const taskTitle = (t) => {
  const src = t.video_url || t.video_file || t.source_name || t.srt_original_name || t.srt_file || ''
  const host = src.replace(/^https?:\/\//, '').split('/')[0]
  return host || src || t.id
}
const platClass = (t) => {
  const s = t.video_url || ''
  if (s.includes('bilibili') || s.includes('b23.tv')) return 'plat-bili'
  if (s.includes('youtube') || s.includes('youtu.be')) return 'plat-yt'
  return 'plat-file'
}
const platChar = (t) => {
  const c = platClass(t)
  return c === 'plat-yt' ? '▶' : c === 'plat-bili' ? 'B' : '▲'
}

async function submit() {
  const v = url.value.trim()
  if (!v) return
  if (!/^https?:\/\//.test(v)) {
    store.error = '请输入有效的 URL（以 http:// 或 https:// 开头）'
    return
  }
  store.error = ''
  await store.addTask(v)
  url.value = ''
}

async function importSrt(event) {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    await store.addSrtTask(file)
  } finally {
    event.target.value = ''
  }
}

async function chooseLocalVideo() {
  const path = await window.electronAPI?.chooseLocalVideo()
  if (path) await store.addLocalVideo(path)
}

onMounted(() => store.loadTasks())
onUnmounted(() => store.cleanup())
</script>

<style scoped>
</style>
