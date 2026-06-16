<template>
  <div class="task-detail">
    <el-page-header @back="$router.push('/')" :content="`任务 ${id}`" />

    <!-- 整体状态 -->
    <el-card class="status-card" v-if="task">
      <div class="status-row">
        <el-tag :type="_tagType(task.status)">{{ task.status }}</el-tag>
        <span class="task-url">{{ task.video_url || task.video_file || '—' }}</span>
      </div>
      <el-progress :percentage="task.progress || 0" :status="_progressStatus(task.status)" />
      <p class="step">{{ task.current_step || task.message || '' }}</p>
      <p class="error" v-if="task.error_message">错误：{{ task.error_message }}</p>
    </el-card>

    <!-- DAG 可视化 -->
    <el-card class="dag-card">
      <template #header><span>Pipeline DAG</span></template>
      <div class="dag-flow">
        <div v-for="node in NODES" :key="node.key" class="dag-node-wrap">
          <div :class="['dag-node', _nodeClass(node.key)]">
            <div class="dag-node-icon">
              <el-icon v-if="nodeStatus(node.key) === 'completed'"><CircleCheck /></el-icon>
              <el-icon v-else-if="nodeStatus(node.key) === 'running'"><Loading /></el-icon>
              <el-icon v-else-if="nodeStatus(node.key) === 'failed'"><CircleClose /></el-icon>
              <el-icon v-else><Clock /></el-icon>
            </div>
            <div class="dag-node-label">{{ node.label }}</div>
            <div class="dag-node-status">{{ nodeStatus(node.key) || '—' }}</div>
            <el-button
              v-if="nodeStatus(node.key) === 'failed' || task?.status === 'completed' || task?.status === 'partial'"
              size="small"
              type="primary"
              plain
              :loading="rerunning === node.key"
              @click="rerunFrom(node.key)"
            >重跑</el-button>
          </div>
          <el-icon class="dag-arrow" v-if="node.key !== 'cleanup'"><Right /></el-icon>
        </div>
      </div>
    </el-card>

    <!-- 产物 -->
    <el-card class="artifacts-card" v-if="artifacts">
      <template #header><span>产物</span></template>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="Markdown 笔记" name="markdown">
          <div class="artifact-content" v-if="artifacts.markdown">
            <el-input type="textarea" :model-value="artifacts.markdown" readonly :rows="18" />
            <el-button size="small" @click="_copy(artifacts.markdown)">复制</el-button>
          </div>
          <el-empty v-else description="暂无笔记" />
        </el-tab-pane>
        <el-tab-pane label="SRT 字幕" name="srt">
          <div class="artifact-content" v-if="artifacts.srt">
            <el-input type="textarea" :model-value="artifacts.srt" readonly :rows="18" />
          </div>
          <el-empty v-else description="暂无字幕" />
        </el-tab-pane>
        <el-tab-pane label="思维导图" name="mindmap">
          <div class="artifact-content" v-if="artifacts.mindmap">
            <pre class="mindmap-pre">{{ artifacts.mindmap }}</pre>
          </div>
          <el-empty v-else description="暂无思维导图" />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getTask, rerunTask } from '../api/task'
import { getProcessResult } from '../api/process'
import { TaskEventSource } from '../api/sse'

const props = defineProps({ id: { type: String, required: true } })

// DAG 节点定义（与后端 NodeName 拓扑一致）
const NODES = [
  { key: 'download', label: '下载视频' },
  { key: 'extract_audio', label: '提取音频' },
  { key: 'transcribe', label: '语音识别' },
  { key: 'organize', label: '整理笔记' },
  { key: 'mindmap', label: '思维导图' },
  { key: 'cleanup', label: '清理' },
]

const task = ref(null)
const nodeStates = ref({}) // { download: 'completed', ... }
const artifacts = ref(null)
const activeTab = ref('markdown')
const rerunning = ref(null)
let es = null

const nodeStatus = (key) => nodeStates.value[key]

const _tagType = (s) => ({ pending: 'info', running: 'warning', completed: 'success', failed: 'danger', partial: 'warning' }[s] || 'info')
const _progressStatus = (s) => (s === 'completed' ? 'success' : s === 'failed' ? 'exception' : '')
const _nodeClass = (key) => `node-${nodeStatus(key) || 'idle'}`
const _copy = async (text) => {
  await navigator.clipboard.writeText(text)
  ElMessage.success('已复制')
}

// 从 SSE 事件映射节点状态
const _applyEvent = (event) => {
  if (!event) return
  if (event.node_name && event.node_status) {
    nodeStates.value = { ...nodeStates.value, [event.node_name]: event.node_status }
  }
  if (event.progress !== undefined && task.value) {
    task.value = { ...task.value, progress: event.progress, current_step: event.message }
  }
  if (event.event_type === 'task.completed' && task.value) {
    task.value = { ...task.value, status: 'completed' }
    _loadResult()
  }
  if (event.event_type === 'task.failed' && task.value) {
    task.value = { ...task.value, status: 'failed' }
  }
}

const rerunFrom = async (nodeKey) => {
  rerunning.value = nodeKey
  try {
    await rerunTask(props.id, nodeKey)
    ElMessage.success(`已从 ${nodeKey} 触发重跑`)
    _subscribe()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    rerunning.value = null
  }
}

const _loadResult = async () => {
  try {
    artifacts.value = await getProcessResult(props.id)
  } catch (e) {
    // 任务未完成时无产物，忽略
  }
}

const _subscribe = () => {
  if (es) es.close()
  es = new TaskEventSource(props.id, _applyEvent, (err) => console.error('SSE', err))
  es.connect()
}

onMounted(async () => {
  try {
    task.value = await getTask(props.id)
    _loadResult()
    _subscribe()
  } catch (e) {
    ElMessage.error('任务不存在')
  }
})

onUnmounted(() => {
  if (es) es.close()
})
</script>

<style scoped>
.task-detail {
  max-width: 1100px;
  margin: 0 auto;
  padding: 20px;
}
.status-card,
.dag-card,
.artifacts-card {
  margin-top: 16px;
}
.status-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.task-url {
  font-size: 13px;
  color: #909399;
  word-break: break-all;
}
.step {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
}
.error {
  color: #f56c6c;
  font-size: 13px;
}
/* DAG 可视化 */
.dag-flow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.dag-node-wrap {
  display: flex;
  align-items: center;
}
.dag-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 110px;
  padding: 12px 8px;
  border: 2px solid #dcdfe6;
  border-radius: 8px;
  gap: 4px;
}
.dag-node-icon {
  font-size: 24px;
}
.dag-node-label {
  font-size: 13px;
  font-weight: 500;
}
.dag-node-status {
  font-size: 11px;
  color: #909399;
}
.dag-arrow {
  font-size: 20px;
  color: #c0c4cc;
  margin: 0 4px;
}
.node-completed {
  border-color: #67c23a;
  background: #f0f9eb;
}
.node-running {
  border-color: #e6a23c;
  background: #fdf6ec;
}
.node-failed {
  border-color: #f56c6c;
  background: #fef0f0;
}
.node-idle {
  border-color: #dcdfe6;
}
.artifact-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mindmap-pre {
  white-space: pre-wrap;
  font-family: monospace;
  font-size: 13px;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  max-height: 400px;
  overflow: auto;
}
</style>
