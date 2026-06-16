import axios from 'axios'

let baseURL = ''

if (typeof window !== 'undefined' && window.electronAPI) {
  window.electronAPI.getBackendUrl().then((url) => {
    baseURL = url + '/api/v1'
  })
} else {
  baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
}

const request = axios.create({
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

request.interceptors.request.use((config) => {
  if (!config.baseURL && baseURL) {
    config.baseURL = baseURL
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

export default request
