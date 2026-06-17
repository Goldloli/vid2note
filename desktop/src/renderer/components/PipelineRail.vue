<template>
  <div>
    <div class="spread" style="margin-bottom:14px">
      <div class="row gap-m">
        <span class="plat-ico" :class="platClass">{{ platChar }}</span>
        <div>
          <div class="row gap-s">
            <strong style="font-size:14px">{{ title }}</strong>
            <span class="badge" :class="badgeClass"><span class="d"></span>{{ statusLabel }}</span>
          </div>
          <div class="muted mono-sm" style="margin-top:3px">{{ source || '—' }}</div>
        </div>
      </div>
      <div class="col" style="align-items:flex-end; gap:4px">
        <span class="mono" style="font-size:16px; font-weight:600" :style="{color: progressColor}">{{ progress }}%</span>
        <router-link v-if="taskId" :to="`/tasks/${taskId}`" class="btn btn-ghost btn-sm" style="padding:0 4px">查看详情 →</router-link>
      </div>
    </div>
    <div class="pipeline-rail">
      <template v-for="(label, i) in NODE_LABELS" :key="label">
        <div class="pr-node" :class="nodeClass(i)">
          <div class="pr-dot">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M20 6L9 17l-5-5"/></svg>
          </div>
          <div class="pr-label">{{ label }}</div>
        </div>
        <div v-if="i < NODE_LABELS.length - 1" class="pr-link" :class="{done: linkDone(i)}"></div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  progress: { type: Number, default: 0 },
  status: { type: String, default: 'pending' },
  title: { type: String, default: '' },
  source: { type: String, default: '' },
  taskId: { type: String, default: '' },
})

const NODE_LABELS = ['下载', '音频', '转录', '笔记', '导图', '清理']
// 与后端节点进度阈值一致（core/pipeline/nodes.py）
const TH = [25, 45, 70, 95, 98, 100]

const currentIndex = computed(() => {
  for (let i = 0; i < TH.length; i++) if (props.progress < TH[i]) return i
  return TH.length - 1
})

const nodeClass = (i) => {
  if (props.status === 'failed' && i === currentIndex.value) return 'failed'
  if (props.progress >= TH[i]) return 'done'
  if (i === currentIndex.value && props.status !== 'completed') return 'active'
  return ''
}
const linkDone = (i) => (i + 1) <= currentIndex.value

const badgeClass = computed(() => {
  const m = { pending: 'pending', running: 'running', completed: 'completed', failed: 'failed' }
  return m[props.status] || 'pending'
})
const statusLabel = computed(() => {
  const m = { pending: '等待中', running: '处理中', completed: '已完成', failed: '失败' }
  return m[props.status] || props.status
})
const progressColor = computed(() => {
  if (props.status === 'failed') return 'var(--danger)'
  if (props.status === 'completed') return 'var(--success)'
  return 'var(--accent)'
})

const platClass = computed(() => {
  const s = props.source || ''
  if (s.includes('bilibili') || s.includes('b23.tv')) return 'plat-bili'
  if (s.includes('youtube') || s.includes('youtu.be')) return 'plat-yt'
  return 'plat-file'
})
const platChar = computed(() => {
  const c = platClass.value
  return c === 'plat-yt' ? '▶' : c === 'plat-bili' ? 'B' : '▲'
})
</script>
