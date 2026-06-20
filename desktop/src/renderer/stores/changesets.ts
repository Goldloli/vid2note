import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as api from '../api/changesets'

export const useChangeSetStore = defineStore('changesets', () => {
  const items = ref<api.ChangeSet[]>([])
  const current = ref<api.ChangeSet | null>(null)
  const loading = ref(false)
  const error = ref<unknown>(null)
  const pendingCount = computed(() => items.value.filter((item) => item.status === 'pending').length)
  async function refresh(): Promise<void> {
    loading.value = true
    try {
      const groups = await Promise.all(
        (['pending', 'applied', 'rejected', 'reverted'] as const).map((status) => api.listChangeSets(status)),
      )
      items.value = groups.flat()
    } catch (cause) {
      error.value = cause
    } finally {
      loading.value = false
    }
  }
  async function approve(id: string, indexes?: number[]): Promise<void> {
    current.value = await api.approveChangeSet(id, indexes)
    await refresh()
  }
  async function reject(id: string, reason: string): Promise<void> {
    current.value = await api.rejectChangeSet(id, reason)
    await refresh()
  }
  async function revert(id: string): Promise<void> {
    current.value = await api.revertChangeSet(id)
    await refresh()
  }
  return { items, current, loading, error, pendingCount, refresh, approve, reject, revert }
})
