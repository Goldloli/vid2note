import { createI18n } from 'vue-i18n'
import zh from './locales/zh.js'
import en from './locales/en.js'

const saved = localStorage.getItem('locale') || 'zh'
document.documentElement.lang = saved

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: saved,
  fallbackLocale: 'zh',
  messages: { zh, en },
})

// 切换语言并同步页面语言属性。
export function setLocale(locale) {
  const g = i18n.global
  g.locale.value = locale
  localStorage.setItem('locale', locale)
  document.documentElement.lang = locale
}
