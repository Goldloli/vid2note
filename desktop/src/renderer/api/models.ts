import { apiClient } from './client'
import type { components } from './generated/schema'

type ProviderListResponse = components['schemas']['ProviderListResponse']
type ModelListResponse = components['schemas']['ModelListResponse']
type OllamaStatusResponse = components['schemas']['OllamaStatusResponse']

export const listModels = (): Promise<ProviderListResponse> =>
  apiClient.get<ProviderListResponse>('/models')

export const listAsrAvailable = (): Promise<ModelListResponse> =>
  apiClient.get<ModelListResponse>('/models/asr/available')

export const listAsrInstalled = (): Promise<ModelListResponse> =>
  apiClient.get<ModelListResponse>('/models/asr/installed')

export const getOllamaStatus = (): Promise<OllamaStatusResponse> =>
  apiClient.get<OllamaStatusResponse>('/models/llm/ollama/status')
