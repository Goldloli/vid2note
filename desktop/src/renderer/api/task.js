import request from './request'

// 任务 API
export const createTask = (videoUrl, opts = {}) =>
  request.post('/tasks', { video_url: videoUrl, ...opts })

export const listTasks = () => request.get('/tasks')

export const getTask = (taskId) => request.get(`/tasks/${taskId}`)

export const rerunTask = (taskId, fromNode = null) =>
  request.post(`/tasks/${taskId}/rerun`, { from_node: fromNode })
