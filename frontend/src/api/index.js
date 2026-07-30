import axios from 'axios'
const api = axios.create({ baseURL: '/api/v1', timeout: 120000 })
api.interceptors.response.use(r => r.data, e => Promise.reject(new Error(e.response?.data?.detail || e.response?.data?.message || e.message || '请求失败')))

export const health = () => api.get('/health')
export const getSettings = () => api.get('/settings')
export const putSettings = (data) => api.put('/settings', data)
export const saveCredential = (provider, field, value) => api.put('/settings/credentials', { provider, field, value })
export const revealCredential = (provider, field) => api.post('/settings/credentials/reveal', { provider, field })
export const clearCredential = (provider, field) => api.delete(`/settings/credentials/${encodeURIComponent(provider)}/${encodeURIComponent(field)}`)
export const testLlm = (provider) => api.post('/settings/llm/test', { provider })
export const storageStats = () => api.get('/storage/stats')

export const createTask = (payload) => {
  // 后端 POST /tasks 用 Form 字段(非 JSON body);object 自动转 FormData
  let fd = payload
  if (!(fd instanceof FormData)) {
    fd = new FormData()
    for (const [k, v] of Object.entries(payload)) {
      if (v !== undefined && v !== null) fd.append(k, v)
    }
  }
  return api.post('/tasks', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
}
export const getTask = (id) => api.get(`/tasks/${id}`)
export const listTasks = (params) => api.get('/tasks', { params })
export const taskStats = () => api.get('/tasks/stats')
export const rerunTask = (id, from) => api.post(`/tasks/${id}/rerun`, null, { params: from ? { from } : {} })
export const cancelTask = (id) => api.post(`/tasks/${id}/cancel`)
export const batchTasks = (task_ids, action) => api.post('/tasks/batch', { task_ids, action })
export const getProductUrl = (id, kind) => `/api/v1/tasks/${id}/products/${kind}`
export const streamTask = (id) => new EventSource(`/api/v1/tasks/${id}/stream`)
export const asrStatus = () => api.get('/asr/status')
export const asrTest = (engine) => api.post('/asr/test', { engine })
