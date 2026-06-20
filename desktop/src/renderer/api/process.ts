import { apiClient } from './client'
import type { components } from './generated/schema'

type StartRequest = components['schemas']['StartRequest']
type StartResponse = components['schemas']['StartResponse']
type StatusResponse = components['schemas']['StatusResponse']
type ResultResponse = components['schemas']['ResultResponse']
type UploadResponse = components['schemas']['UploadResponse']

export const startProcess = (payload: Partial<StartRequest>): Promise<StartResponse> =>
  apiClient.post<StartResponse, Partial<StartRequest>>('/process/start', payload)

export const getProcessStatus = (taskId: string): Promise<StatusResponse> =>
  apiClient.get<StatusResponse>(`/process/status/${taskId}`)

export const getProcessResult = (taskId: string): Promise<ResultResponse> =>
  apiClient.get<ResultResponse>(`/process/result/${taskId}`)

export const uploadSrt = (file: File): Promise<UploadResponse> => {
  const form = new FormData()
  form.append('file', file)
  return apiClient.post<UploadResponse, FormData>('/upload/srt', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
