import request from './request'

// 配置 API
export const getConfig = () => request.get('/config')

export const updateConfig = (payload) => request.put('/config', payload)

export const verifyApiKey = (provider, apiKey) =>
  request.post('/config/verify', { provider, api_key: apiKey })
