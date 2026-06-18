import request from './request'

// 任务 API
// export_mindmap 默认 true：思维导图是核心产物，除非显式关闭
export const createTask = (videoUrl, opts = {}) =>
  request.post('/tasks', {
    video_url: videoUrl,
    export_mindmap: opts.export_mindmap ?? true,
    asr_provider: opts.asr_provider,
    llm_provider: opts.llm_provider,
    ...opts,
  })

export const listTasks = () => request.get('/tasks')

export const getTask = (taskId) => request.get(`/tasks/${taskId}`)

export const rerunTask = (taskId, fromNode = null) =>
  request.post(`/tasks/${taskId}/rerun`, { from_node: fromNode })
