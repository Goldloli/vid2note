import request from './request'

// 模型 API（ASR 模型管理、Ollama 状态）
export const listModels = () => request.get('/models')

export const listAsrAvailable = () => request.get('/models/asr/available')

export const listAsrInstalled = () => request.get('/models/asr/installed')

export const getOllamaStatus = () => request.get('/models/llm/ollama/status')
