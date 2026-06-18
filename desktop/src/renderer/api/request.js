import axios from 'axios'

// 后端地址：异步解析（通过 preload IPC 从主进程获取）
let _baseURL = ''
let _baseURLPromise = null

function resolveBaseURL() {
  if (_baseURLPromise) return _baseURLPromise
  _baseURLPromise = (async () => {
    if (typeof window !== 'undefined' && window.electronAPI) {
      try {
        const url = await window.electronAPI.getBackendUrl()
        _baseURL = url + '/api/v1'
      } catch (e) {
        _baseURL = '/api/v1'
      }
    } else {
      _baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
    }
    return _baseURL
  })()
  return _baseURLPromise
}

resolveBaseURL()

const request = axios.create({
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

request.interceptors.request.use(async (config) => {
  if (!config.baseURL) {
    await resolveBaseURL()
    config.baseURL = _baseURL
  }
  return config
})

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const msg = error.response?.data?.error || error.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

/** 返回已解析的 baseURL（含 /api/v1），用于构造下载链接等非 axios 场景。 */
export async function getBaseURL() {
  await resolveBaseURL()
  return _baseURL
}

export default request
