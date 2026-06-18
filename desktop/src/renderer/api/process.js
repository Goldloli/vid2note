import request from './request'

// 处理 API（启动、状态、产物）
export const startProcess = (payload) => request.post('/process/start', payload)

export const getProcessStatus = (taskId) => request.get(`/process/status/${taskId}`)

export const getProcessResult = (taskId) => request.get(`/process/result/${taskId}`)

export const uploadSrt = (file) => {
  const form = new FormData()
  form.append('file', file)
  return request.post('/upload/srt', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
