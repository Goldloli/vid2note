import { apiClient } from './client'
import type { components } from './generated/schema'

export type ChangeSet = components['schemas']['ChangeSet']
export type ChangeSetStatus = ChangeSet['status']

export const listChangeSets = (status: ChangeSetStatus = 'pending'): Promise<ChangeSet[]> =>
  apiClient.get('/changesets', { params: { status } })
export const getChangeSet = (id: string): Promise<ChangeSet> => apiClient.get(`/changesets/${id}`)
export const approveChangeSet = (id: string, operationIndexes?: number[]): Promise<ChangeSet> =>
  apiClient.post(`/changesets/${id}/approve`, { operation_indexes: operationIndexes })
export const rejectChangeSet = (id: string, reason: string): Promise<ChangeSet> =>
  apiClient.post(`/changesets/${id}/reject`, { reason })
export const revertChangeSet = (id: string): Promise<ChangeSet> =>
  apiClient.post(`/changesets/${id}/revert`)
