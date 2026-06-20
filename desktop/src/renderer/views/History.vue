<template>
  <div class="page">
    <div class="page-head"><h1>历史</h1><div class="sub">{{ filtered.length }} 个任务 · {{ store.tasks.length }} 累计</div></div>

    <!-- 筛选栏 -->
    <div class="hist-bar">
      <button v-for="f in filters" :key="f.key" class="chip" :class="{active: filter === f.key}" @click="filter = f.key">{{ f.label }}</button>
      <div class="search" style="margin-left:auto;min-width:220px">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>
        <input v-model="query" placeholder="搜索任务、链接…">
      </div>
    </div>

    <!-- 表格 -->
    <div class="card" style="overflow:hidden">
      <div class="table">
        <table>
          <thead><tr><th>来源</th><th>状态</th><th>进度</th><th>创建时间</th><th style="text-align:right">操作</th></tr></thead>
          <tbody>
            <tr v-for="task in paged" :key="task.id">
              <td>
                <div class="src-cell">
                  <span class="plat-ico" :class="platClass(task)">{{ platChar(task) }}</span>
                  <div><div style="font-weight:500">{{ taskTitle(task) }}</div><div class="muted mono-sm">{{ task.video_url || task.video_file || '—' }}</div></div>
                </div>
              </td>
              <td><span class="badge" :class="badgeClass(task.status)"><span class="d"></span>{{ statusLabel(task.status) }}</span></td>
              <td class="mono-sm muted">{{ task.progress || 0 }}%</td>
              <td class="mono-sm muted">{{ fmtTime(task.created_at) }}</td>
              <td><div class="row gap-xs" style="justify-content:flex-end">
                <router-link :to="`/workspace/tasks/${task.id}`" class="btn btn-sm">详情</router-link>
                <router-link v-if="task.status === 'completed'" :to="`/workspace/note/${task.id}`" class="btn btn-sm">笔记</router-link>
              </div></td>
            </tr>
            <tr v-if="!paged.length"><td colspan="5" class="muted" style="text-align:center;padding:24px">暂无任务</td></tr>
          </tbody>
        </table>
      </div>
      <!-- 分页 -->
      <div class="pager" v-if="filtered.length > pageSize">
        <span class="p-info">{{ (page-1)*pageSize+1 }}–{{ Math.min(page*pageSize, filtered.length) }} / {{ filtered.length }}</span>
        <button :disabled="page <= 1" @click="page--">‹</button>
        <button v-for="p in totalPages" :key="p" :class="{active: p === page}" @click="page = p">{{ p }}</button>
        <button :disabled="page >= totalPages" @click="page++">›</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useTaskStore } from '../stores/task'

const store = useTaskStore()
const filter = ref('all')
const query = ref('')
const page = ref(1)
const pageSize = 12

const filters = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '失败' },
  { key: 'interrupted', label: '已中断' },
]

const filtered = computed(() => {
  let list = store.tasks
  if (filter.value !== 'all') {
    if (filter.value === 'running') list = list.filter((t) => t.status === 'running' || t.status === 'pending')
    else list = list.filter((t) => t.status === filter.value)
  }
  const q = query.value.toLowerCase().trim()
  if (q) list = list.filter((t) => (t.video_url || t.video_file || t.srt_original_name || t.id).toLowerCase().includes(q))
  return list
})
const totalPages = computed(() => Math.ceil(filtered.value.length / pageSize) || 1)
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))

const taskTitle = (t) => { const s = t.video_url || t.video_file || t.srt_original_name || ''; return s.replace(/^https?:\/\//, '').split('/')[0] || t.id }
const platClass = (t) => { const s = t.video_url || ''; if (s.includes('bilibili')||s.includes('b23.tv')) return 'plat-bili'; if (s.includes('youtube')||s.includes('youtu.be')) return 'plat-yt'; return 'plat-file' }
const platChar = (t) => { const c = platClass(t); return c === 'plat-yt' ? '▶' : c === 'plat-bili' ? 'B' : '▲' }
const statusLabel = (s) => ({ pending: '等待', running: '进行中', completed: '已完成', failed: '失败', interrupted: '已中断', partial: '部分完成' }[s] || s)
const badgeClass = (s) => ({ pending: 'pending', running: 'running', completed: 'completed', failed: 'failed', interrupted: 'warn', partial: 'warn' }[s] || 'pending')
const fmtTime = (t) => { if (!t) return '—'; try { return new Date(t).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' }) } catch { return String(t).slice(0,16) } }

onMounted(() => store.loadTasks())
</script>

<style scoped>
.hist-bar { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:18px; }
.pager { display:flex; align-items:center; gap:6px; justify-content:flex-end; padding:14px 14px; }
.pager .p-info { margin-right:auto; font-size:12.5px; color:var(--muted); }
.pager button { width:30px; height:30px; border-radius:7px; border:1px solid var(--border); background:var(--surface); color:var(--muted); font-size:12.5px; font-family:var(--font-mono); }
.pager button.active { background:var(--accent); border-color:var(--accent); color:var(--accent-fg); }
.pager button[disabled] { opacity:0.4; }
</style>
