import { createI18n } from 'vue-i18n'
import zh from './locales/zh.js'
import en from './locales/en.js'

const saved = localStorage.getItem('locale') || 'zh'
document.documentElement.lang = saved

export const i18n = createI18n({
  legacy: true,            // template 直接 $t('key'),无需每组件 useI18n
  locale: saved,
  fallbackLocale: 'zh',
  messages: { zh, en },
})

// 切换语言(兼容 legacy 下 global.locale 为 ref 或字符串的不同版本)
export function setLocale(locale) {
  const g = i18n.global
  if (g.locale && typeof g.locale === 'object' && 'value' in g.locale) g.locale.value = locale
  else g.locale = locale
  localStorage.setItem('locale', locale)
  document.documentElement.lang = locale
}
