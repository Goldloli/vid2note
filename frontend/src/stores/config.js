import { defineStore } from 'pinia'
import { getSettings as apiGet, health as apiHealth } from '@/api'
import { setLocale } from '@/i18n'
export const useConfigStore = defineStore('config', {
  state: () => ({
    settings: null,
    health: null,
    theme: localStorage.getItem('theme') || 'light',
    locale: localStorage.getItem('locale') || 'zh',
  }),
  actions: {
    async fetchAll() {
      try { this.settings = await apiGet() } catch (e) {}
      try { this.health = await apiHealth() } catch (e) {}
    },
    applyTheme() { document.documentElement.setAttribute('data-theme', this.theme) },
    toggleTheme() {
      this.theme = this.theme === 'light' ? 'dark' : 'light'
      localStorage.setItem('theme', this.theme); this.applyTheme()
    },
    changeLocale(v) { this.locale = v; setLocale(v) },
  }
})
