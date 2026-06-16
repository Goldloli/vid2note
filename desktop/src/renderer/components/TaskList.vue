<template>
  <div class="task-list">
    <el-card>
      <template #header>
        <span>任务列表</span>
      </template>
      <el-empty v-if="store.tasks.length === 0" description="暂无任务" />
      <div v-else class="task-items">
        <div
          v-for="task in store.tasks"
          :key="task.id"
          class="task-item clickable"
          @click="goDetail(task.id)"
        >
          <div class="task-header">
            <span class="task-id">{{ task.id }}</span>
            <el-tag :type="_tagType(task.status)" size="small">{{ task.status }}</el-tag>
          </div>
          <p class="task-url">{{ task.video_url || task.video_file }}</p>
          <p class="task-step">{{ task.current_step }}</p>
          <el-progress :percentage="task.progress || 0" :status="_progressStatus(task.status)" />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useTaskStore } from '../stores/task'

const store = useTaskStore()
const router = useRouter()

const goDetail = (taskId) => router.push(`/tasks/${taskId}`)

const _tagType = (status) => {
  const map = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger' }
  return map[status] || 'info'
}

const _progressStatus = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return ''
}
</script>

<style scoped>
.task-list {
  margin-top: 20px;
}
.task-items {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.task-item {
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
}
.task-item.clickable {
  cursor: pointer;
  transition: border-color 0.2s;
}
.task-item.clickable:hover {
  border-color: #409eff;
}
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.task-id {
  font-family: monospace;
  font-size: 13px;
  color: #606266;
}
.task-url {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
  word-break: break-all;
}
.task-step {
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}
</style>
