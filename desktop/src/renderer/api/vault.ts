import { apiClient } from './client'
import type { components } from './generated/schema'

export type VaultPage = components['schemas']['VaultPage']
export type VaultTreeEntry = components['schemas']['VaultTreeEntry']
export type VaultSearchResult = components['schemas']['VaultSearchResult']
export type SourceRecord = components['schemas']['SourceRecord']
export type VaultBacklink = components['schemas']['VaultBacklink']

export const listVaultTree = (): Promise<VaultTreeEntry[]> => apiClient.get('/vault/tree')
export const readVaultPage = (path: string): Promise<VaultPage> =>
  apiClient.get('/vault/page', { params: { path } })
export const updateVaultPage = (path: string, content: string, baseHash: string): Promise<VaultPage> =>
  apiClient.put('/vault/page', { content, base_hash: baseHash }, { params: { path } })
export const searchVault = (query: string): Promise<VaultSearchResult[]> =>
  apiClient.get('/vault/search', { params: { q: query } })
export const listBacklinks = (path: string): Promise<VaultBacklink[]> =>
  apiClient.get('/vault/backlinks', { params: { path } })
export const readSource = (sourceId: string): Promise<SourceRecord> =>
  apiClient.get(`/sources/${encodeURIComponent(sourceId)}`)
