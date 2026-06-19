import { ref } from 'vue'
import { defineStore } from 'pinia'

import * as api from '../api/media'

export const useMediaStore = defineStore('media', () => {
  const current = ref<api.MediaReference | null>(null)
  const error = ref<unknown>(null)
  async function frame(sourceId: string, timestampMs: number): Promise<void> {
    error.value = null
    try { current.value = await api.getFrame(sourceId, timestampMs) } catch (cause) { current.value = null; error.value = cause }
  }
  async function clip(sourceId: string, startMs: number, endMs: number): Promise<void> {
    error.value = null
    try { current.value = await api.getClip(sourceId, startMs, endMs) } catch (cause) { current.value = null; error.value = cause }
  }
  return { current, error, frame, clip }
})
