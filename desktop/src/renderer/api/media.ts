import { apiClient } from './client'
import type { components } from './generated/schema'

export type MediaReference = components['schemas']['MediaReference']
export const getFrame = (sourceId: string, timestampMs: number): Promise<MediaReference> =>
  apiClient.get('/media/frame', { params: { source_id: sourceId, timestamp_ms: timestampMs } })
export const getClip = (
  sourceId: string,
  startMs: number,
  endMs: number,
  bufferMs = 1500,
): Promise<MediaReference> =>
  apiClient.get('/media/clip', {
    params: { source_id: sourceId, start_ms: startMs, end_ms: endMs, buffer_ms: bufferMs },
  })
