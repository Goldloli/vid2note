const HTML_START_RE = /^\s*(?:<!doctype\s+html\b|<html\b)/i
const LOCAL_SCREENSHOT_RE = /(?:^|\/)shot_\d+\.(?:png|jpe?g|webp)$/i

export class ProductReadError extends Error {
  constructor(message, reason = 'request-failed', status = 0) {
    super(message)
    this.name = 'ProductReadError'
    this.reason = reason
    this.status = status
  }
}

/**
 * 读取文本产物并区分“未就绪/已清理”和真正的网络错误。
 * available=false 时不发请求，避免 SPA 回退页被误当作产物。
 */
export async function readProductText({
  url,
  available = true,
  fetchImpl = globalThis.fetch,
}) {
  if (!available) return { state: 'unavailable', text: '' }
  let response
  try {
    response = await fetchImpl(url, {
      headers: { Accept: 'text/plain, text/markdown;q=0.9, */*;q=0.1' },
    })
  } catch (error) {
    throw new ProductReadError(error?.message || '产物请求失败')
  }

  if (response.status === 404) return { state: 'missing', text: '' }
  if (!response.ok) {
    throw new ProductReadError(
      `产物请求失败 (${response.status})`,
      'http-error',
      response.status,
    )
  }

  const contentType = String(response.headers?.get?.('content-type') || '').toLowerCase()
  const text = await response.text()
  if (
    contentType.includes('text/html')
    || contentType.includes('application/json')
    || HTML_START_RE.test(text)
  ) {
    throw new ProductReadError(
      '服务返回的不是可阅读产物',
      'invalid-content',
      response.status,
    )
  }
  return { state: 'ready', text }
}

function fileName(path) {
  const clean = String(path || '').split(/[?#]/)[0].replace(/^<|>$/g, '')
  return clean.split(/[\\/]/).pop() || ''
}

function isExternalDestination(destination) {
  return /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i.test(destination)
}

/**
 * 把当前任务已登记的截图相对链接映射为受控产品 URL。
 * 只按当前任务 screenshot_paths 中的 basename 匹配，兼容历史含 ".." 的路径。
 */
export function rewriteTaskScreenshotLinks(markdown, taskId, screenshotPaths = []) {
  const indexes = new Map()
  screenshotPaths.forEach((path, index) => {
    const name = fileName(path)
    if (name && LOCAL_SCREENSHOT_RE.test(name) && !indexes.has(name)) {
      indexes.set(name, index)
    }
  })
  if (!indexes.size) return String(markdown ?? '')

  const encodedTaskId = encodeURIComponent(String(taskId || ''))
  return String(markdown ?? '').replace(
    /(!\[[^\]]*]\()(<)?([^\s)>]+)(>)?([^)]*\))/g,
    (match, prefix, open, destination, close, suffix) => {
      if (isExternalDestination(destination)) return match
      const index = indexes.get(fileName(destination))
      if (index == null) return match
      const url = `/api/v1/tasks/${encodedTaskId}/products/screenshot?index=${index}`
      return `${prefix}${open || ''}${url}${close || ''}${suffix}`
    },
  )
}

export function noteImageError(event, label = '截图暂时无法显示') {
  const image = event?.target
  if (!image || String(image.tagName).toLowerCase() !== 'img') return
  const fallback = image.ownerDocument.createElement('span')
  fallback.className = 'note-image-error'
  fallback.setAttribute('role', 'status')
  fallback.textContent = label
  image.replaceWith(fallback)
}
