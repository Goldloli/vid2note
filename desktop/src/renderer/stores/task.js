import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { createTask, listTasks } from '../api/task'
import { startProcess, uploadSrt } from '../api/process'
import { TaskEventSource } from '../api/sse'

export const useTaskStore = defineStore('task', () => {
  const tasks = ref([])
  const isCreating = ref(false)
  const error = ref('')
  const eventSources = ref(new Map())
  const taskMutationVersions = new Map()
  let mutationVersion = 0
  let latestLoadRequest = 0

  const runningTasks = computed(() => tasks.value.filter((t) => t.status === 'running' || t.status === 'pending'))
  const completedTasks = computed(() => tasks.value.filter((t) => t.status === 'completed'))

  async function loadTasks() {
    const loadRequest = ++latestLoadRequest
    const requestVersion = mutationVersion
    try {
      const res = await listTasks()
      if (loadRequest !== latestLoadRequest) return
      const remoteTasks = res.tasks || []
      const remoteIds = new Set(remoteTasks.map((task) => task.id))
      const localById = new Map(tasks.value.map((task) => [task.id, task]))
      const createdWhileLoading = tasks.value.filter(
        (task) =>
          !remoteIds.has(task.id) &&
          (taskMutationVersions.get(task.id) || 0) > requestVersion,
      )
      const mergedRemote = remoteTasks.map((task) =>
        (taskMutationVersions.get(task.id) || 0) > requestVersion
          ? (localById.get(task.id) || task)
          : task,
      )
      tasks.value = [...createdWhileLoading, ...mergedRemote]
    } catch (e) {
      if (loadRequest === latestLoadRequest) error.value = e.message
    }
  }

  async function addTask(url) {
    isCreating.value = true
    error.value = ''
    try {
      const res = await createTask(url)
      const newTask = {
        id: res.task_id,
        status: 'pending',
        progress: 0,
        current_step: '等待处理',
        video_url: url,
        created_at: new Date().toISOString(),
      }
      tasks.value = [newTask, ...tasks.value]
      _markTaskMutation(res.task_id)
      _subscribeToEvents(res.task_id)
      return res.task_id
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      isCreating.value = false
    }
  }

  async function addSrtTask(file) {
    isCreating.value = true
    error.value = ''
    try {
      const uploaded = await uploadSrt(file)
      const res = await startProcess({
        srt_file: uploaded.file_id,
        llm_provider: 'mock',
        asr_provider: 'funasr',
      })
      const newTask = {
        id: res.task_id,
        status: 'pending',
        progress: 0,
        current_step: '等待处理',
        srt_file: uploaded.file_id,
        source_name: uploaded.filename,
        created_at: new Date().toISOString(),
      }
      tasks.value = [newTask, ...tasks.value]
      _markTaskMutation(res.task_id)
      _subscribeToEvents(res.task_id)
      return res.task_id
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      isCreating.value = false
    }
  }

  async function addLocalVideo(path) {
    isCreating.value = true
    error.value = ''
    try {
      const res = await startProcess({ video_file: path, asr_provider: 'funasr' })
      tasks.value = [{ id: res.task_id, status: 'pending', progress: 0, current_step: '等待处理', video_file: path, created_at: new Date().toISOString() }, ...tasks.value]
      _markTaskMutation(res.task_id)
      _subscribeToEvents(res.task_id)
      return res.task_id
    } catch (e) {
      error.value = e.message
      throw e
    } finally {
      isCreating.value = false
    }
  }

  function _markTaskMutation(taskId) {
    taskMutationVersions.set(taskId, ++mutationVersion)
  }

  function _subscribeToEvents(taskId) {
    if (eventSources.value.has(taskId)) {
      eventSources.value.get(taskId).close()
    }

    const es = new TaskEventSource(
      taskId,
      (event) => _handleEvent(taskId, event),
      (err) => console.error('SSE error for', taskId, err)
    )
    es.connect()
    eventSources.value.set(taskId, es)
  }

  function _handleEvent(taskId, event) {
    const idx = tasks.value.findIndex((t) => t.id === taskId)
    if (idx === -1) return

    const task = tasks.value[idx]
    const updated = {
      ...task,
      progress: event.progress !== undefined ? event.progress : task.progress,
      current_step: event.message || task.current_step,
      status: _mapStatus(event.event_type, event.node_status) || task.status,
    }
    tasks.value = [...tasks.value.slice(0, idx), updated, ...tasks.value.slice(idx + 1)]
    _markTaskMutation(taskId)

    if (
      event.event_type === 'task.completed' ||
      event.event_type === 'task.failed' ||
      event.event_type === 'task.interrupted'
    ) {
      const es = eventSources.value.get(taskId)
      if (es) {
        es.close()
        eventSources.value.delete(taskId)
      }
    }
  }

  function _mapStatus(eventType, nodeStatus) {
    if (eventType === 'task.started') return 'running'
    if (eventType === 'task.completed') return 'completed'
    if (eventType === 'task.failed') return 'failed'
    if (eventType === 'task.interrupted') return 'interrupted'
    if (eventType.startsWith('node.')) {
      if (nodeStatus === 'running') return 'running'
      if (nodeStatus === 'failed') return 'failed'
    }
    return null
  }

  function cleanup() {
    eventSources.value.forEach((es) => es.close())
    eventSources.value.clear()
  }

  return {
    tasks,
    isCreating,
    error,
    runningTasks,
    completedTasks,
    loadTasks,
    addTask,
    addSrtTask,
    addLocalVideo,
    cleanup,
  }
})
