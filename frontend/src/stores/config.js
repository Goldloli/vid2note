import { defineStore } from 'pinia'
import { getSettings as apiGet, health as apiHealth, putSettings as apiPut } from '@/api'
import { setLocale } from '@/i18n'

const THEMES = new Set(['system', 'light', 'dark'])
const BACKGROUNDS = new Set(['mesh', 'static', 'plain'])
const LOCALES = new Set(['zh', 'en'])

function stored(key, allowed, fallback) {
  const value = localStorage.getItem(key)
  return allowed.has(value) ? value : fallback
}

export const useConfigStore = defineStore('config', {
  state: () => ({
    settings: null,
    health: null,
    theme: stored('theme', THEMES, 'system'),
    locale: stored('locale', LOCALES, 'zh'),
    background: stored('background', BACKGROUNDS, 'plain'),
  }),
  actions: {
    async fetchAll() {
      await Promise.all([
        apiGet().then(response => this.adoptSettings(response)).catch(() => {}),
        apiHealth().then(response => { this.health = response }).catch(() => {}),
      ])
    },
    adoptSettings(response) {
      if (!response?.settings) return
      this.settings = response
      const values = response.settings
      if (this.health?.engines) {
        this.health = {
          ...this.health,
          engines: {
            ...this.health.engines,
            asr_engine: values['asr.engine'] || this.health.engines.asr_engine,
            llm_model: values['llm.model'] || this.health.engines.llm_model,
          },
        }
      }
      if (LOCALES.has(values['ui.language'])) this.changeLocale(values['ui.language'])
      if (THEMES.has(values['ui.theme'])) this.setTheme(values['ui.theme'])
      if (BACKGROUNDS.has(values['ui.background'])) this.setBackground(values['ui.background'])
    },
    applyAppearance() {
      this.applyTheme()
      this.applyBackground()
    },
    applyTheme() {
      const resolved = this.theme === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : this.theme
      document.documentElement.dataset.themePreference = this.theme
      document.documentElement.dataset.theme = resolved
    },
    applyBackground() {
      document.documentElement.dataset.background = this.background
    },
    setTheme(value) {
      this.theme = THEMES.has(value) ? value : 'system'
      localStorage.setItem('theme', this.theme)
      this.applyTheme()
    },
    setBackground(value) {
      this.background = BACKGROUNDS.has(value) ? value : 'plain'
      localStorage.setItem('background', this.background)
      this.applyBackground()
    },
    async toggleTheme() {
      const previous = this.theme
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'
      this.setTheme(next)
      try {
        this.adoptSettings(await apiPut({ 'ui.theme': next }))
      } catch {
        this.setTheme(previous)
      }
    },
    changeLocale(value) {
      this.locale = LOCALES.has(value) ? value : 'zh'
      setLocale(this.locale)
    },
  }
})
