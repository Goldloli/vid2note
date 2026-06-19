import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as vaultApi from '../api/vault'

export const useVaultStore = defineStore('vault', () => {
  const tree = ref<vaultApi.VaultTreeEntry[]>([])
  const currentPage = ref<vaultApi.VaultPage | null>(null)
  const searchResults = ref<vaultApi.VaultSearchResult[]>([])
  const backlinks = ref<vaultApi.VaultBacklink[]>([])
  const loading = ref(false)
  const error = ref<unknown>(null)
  let request = 0

  async function refreshTree(): Promise<void> {
    try {
      tree.value = await vaultApi.listVaultTree()
    } catch (cause) {
      error.value = cause
    }
  }
  async function open(path: string): Promise<void> {
    const token = ++request
    loading.value = true
    error.value = null
    try {
      const page = await vaultApi.readVaultPage(path)
      let pageBacklinks: vaultApi.VaultBacklink[] = []
      try {
        pageBacklinks = await vaultApi.listBacklinks(path)
      } catch {
        pageBacklinks = []
      }
      if (token === request) {
        currentPage.value = page
        backlinks.value = pageBacklinks
      }
    } catch (cause) {
      if (token === request) error.value = cause
    } finally {
      if (token === request) loading.value = false
    }
  }
  async function save(content: string): Promise<void> {
    if (!currentPage.value) return
    currentPage.value = await vaultApi.updateVaultPage(
      currentPage.value.path,
      content,
      currentPage.value.content_hash,
    )
  }
  async function search(query: string): Promise<void> {
    try {
      searchResults.value = query.trim() ? await vaultApi.searchVault(query.trim()) : []
    } catch (cause) {
      error.value = cause
    }
  }
  return { tree, currentPage, searchResults, backlinks, loading, error, refreshTree, open, save, search }
})
