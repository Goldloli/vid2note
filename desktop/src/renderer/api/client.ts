import axios, { type AxiosRequestConfig } from 'axios'

import { toApiError } from './errors'

let baseURL = ''
let baseURLPromise: Promise<string> | null = null
let accessToken: string | null = import.meta.env.VITE_API_TOKEN || null

function resolveBaseURL(): Promise<string> {
  if (baseURLPromise) return baseURLPromise
  baseURLPromise = (async () => {
    if (typeof window !== 'undefined' && window.electronAPI) {
      try {
        const connection = await window.electronAPI.getBackendConnection()
        baseURL = `${connection.baseUrl}/api/v1`
        accessToken = connection.token
      } catch {
        baseURL = '/api/v1'
      }
    } else {
      baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
    }
    return baseURL
  })()
  return baseURLPromise
}

const axiosClient = axios.create({
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

axiosClient.interceptors.request.use(async (config) => {
  if (!config.baseURL) config.baseURL = await resolveBaseURL()
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

axiosClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(toApiError(error)),
)

export const apiClient = {
  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await axiosClient.get<T>(url, config)
    return response.data
  },
  async post<T, TBody = unknown>(
    url: string,
    body?: TBody,
    config?: AxiosRequestConfig,
  ): Promise<T> {
    const response = await axiosClient.post<T>(url, body, config)
    return response.data
  },
  async put<T, TBody = unknown>(url: string, body: TBody, config?: AxiosRequestConfig): Promise<T> {
    const response = await axiosClient.put<T>(url, body, config)
    return response.data
  },
}

export function setApiToken(token: string | null): void {
  accessToken = token
}

export async function getBaseURL(): Promise<string> {
  return resolveBaseURL()
}

export async function getApiConnection(): Promise<{ baseURL: string; token: string | null }> {
  return { baseURL: await resolveBaseURL(), token: accessToken }
}

export async function fetchApiBlobUrl(path: string): Promise<string> {
  const { baseURL: resolvedBaseURL, token } = await getApiConnection()
  const response = await fetch(`${resolvedBaseURL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw new Error(`Protected asset request failed (${response.status})`)
  return URL.createObjectURL(await response.blob())
}
