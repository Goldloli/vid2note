import axios, { type AxiosRequestConfig } from 'axios'

import { toApiError } from './errors'

let baseURL = ''
let baseURLPromise: Promise<string> | null = null
let accessToken: string | null = null

function resolveBaseURL(): Promise<string> {
  if (baseURLPromise) return baseURLPromise
  baseURLPromise = (async () => {
    if (typeof window !== 'undefined' && window.electronAPI) {
      try {
        baseURL = `${await window.electronAPI.getBackendUrl()}/api/v1`
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

void resolveBaseURL()
