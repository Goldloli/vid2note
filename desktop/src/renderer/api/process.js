import request from './request'

// 处理 API（启动、状态、产物）
export const startProcess = (payload) => request.post('/process/start', payload)

export const getProcessStatus = (taskId) => request.get(`/process/status/${taskId}`)

export const getProcessResult = (taskId) => request.get(`/process/result/${taskId}`)
