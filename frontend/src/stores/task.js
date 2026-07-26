import { defineStore } from 'pinia'
import { createTask as apiCreate, listTasks as apiList } from '@/api'
export const useTaskStore = defineStore('task', {
  state: () => ({ items: [], total: 0 }),
  actions: {
    async fetchRecent() {
      const res = await apiList({ page: 1, page_size: 30 })
      this.items = res.items || []; this.total = res.total || 0
    },
    async create(payload) { return await apiCreate(payload) }
  },
  getters: {
    running: (s) => s.items.filter(t => t.status === 'running' || t.status === 'pending'),
    completed: (s) => s.items.filter(t => t.status === 'completed').slice(0, 10)
  }
})
