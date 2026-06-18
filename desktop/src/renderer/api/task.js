import request, { getBaseURL } from './request'

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

// 列出任务所有产物
export const listArtifacts = (taskId) => request.get(`/tasks/${taskId}/artifacts`)

// 触发浏览器下载单个产物（原始字节 + 正确 Content-Type）
export async function downloadArtifact(taskId, key) {
  const base = await getBaseURL()
  const a = document.createElement('a')
  a.href = `${base}/tasks/${taskId}/artifacts/${key}`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}

// 一键导出全部产物为 zip
export async function exportAllArtifacts(taskId) {
  const base = await getBaseURL()
  const a = document.createElement('a')
  a.href = `${base}/tasks/${taskId}/export`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}
