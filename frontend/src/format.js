// 统一列表命名:MM-DD 标题 · 来源(openspec change frontend-unified-list-naming)
import { i18n } from '@/i18n'

const VIDEO_EXTS = /\.(mp4|mkv|mov|webm|avi|flv|wmv|m4v|mp3|m4a|wav|aac|flac|ogg|txt|srt)$/i

function mmdd(d) {
  if (!d) return ''
  const m = String(d).match(/(\d{2})-(\d{2})/)
  return m ? `${m[1]}-${m[2]}` : ''
}

function videoId(t) {
  const st = t.source_type || '', url = t.source_url || ''
  if (st === 'youtube') { const m = url.match(/(?:v=|youtu\.be\/)([\w-]{6,})/); return m ? m[1] : '' }
  if (st === 'bilibili') { const m = url.match(/(BV[\w]+)/); return m ? m[1] : '' }
  if (st === 'direct') { try { return new URL(url).hostname } catch (e) { return '' } }
  return ''
}

function sourceName(st) {
  const t = i18n.global.t
  return ({
    youtube: t('source.youtube'),
    bilibili: t('source.bilibili'),
    direct: t('source.direct'),
    local_video: t('source.localVideo'),
    local_audio: t('source.localAudio'),
  })[st] || st || ''
}

export function displayName(t) {
  const title = (t.title || '').trim().replace(VIDEO_EXTS, '').trim()
  const name = title || i18n.global.t('source.unnamed')
  return `${mmdd(t.finished_at || t.created_at)} ${name} · ${sourceName(t.source_type)}`
}
