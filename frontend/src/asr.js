// ASR 引擎与策略的统一文案常量(openspec change asr-management-page)
// l / desc 存 i18n key,组件用 $t(e.l) / $t(e.desc) 渲染(支持中英文,openspec change frontend-i18n)
// 在线 ASR 对外统一称「bcut」
export const ASR_ENGINES = [
  { v: 'bcut', l: 'engine.bcut.l', desc: 'engine.bcut.desc', online: true },
  { v: 'whisper_cpp', l: 'engine.whisper_cpp.l', desc: 'engine.whisper_cpp.desc', online: false },
  { v: 'external', l: 'engine.external.l', desc: 'engine.external.desc', online: false },
]
export const ASR_STRATEGIES = [
  { v: 'online_first', l: 'engine.online_first.l' },
  { v: 'single', l: 'engine.single.l' },
]
// 返回引擎的 i18n key(调用方需 $t)
export const asrLabelKey = (v) => ASR_ENGINES.find(e => e.v === v)?.l || v
