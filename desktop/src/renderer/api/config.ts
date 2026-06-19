import { apiClient } from './client'
import type { components } from './generated/schema'

type ConfigResponse = components['schemas']['ConfigResponse']
type UpdateConfigRequest = components['schemas']['UpdateConfigRequest']
type ConfigUpdateResponse = components['schemas']['ConfigUpdateResponse']
type VerifyKeyResponse = components['schemas']['VerifyKeyResponse']

export const getConfig = (): Promise<ConfigResponse> => apiClient.get<ConfigResponse>('/config')

export const updateConfig = (payload: UpdateConfigRequest): Promise<ConfigUpdateResponse> =>
  apiClient.put<ConfigUpdateResponse, UpdateConfigRequest>('/config', payload)

export const verifyApiKey = (provider: string, apiKey: string): Promise<VerifyKeyResponse> =>
  apiClient.post<VerifyKeyResponse, components['schemas']['VerifyKeyRequest']>('/config/verify', {
    provider,
    api_key: apiKey,
  })
