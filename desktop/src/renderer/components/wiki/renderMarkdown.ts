import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

type RenderEnvironment = { headingIds: Map<string, number> }

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })

markdown.inline.ruler.before('link', 'wikilink', (state, silent) => {
  if (!state.src.startsWith('[[', state.pos)) return false
  const end = state.src.indexOf(']]', state.pos + 2)
  if (end < 0) return false
  const value = state.src.slice(state.pos + 2, end)
  const separator = value.indexOf('|')
  const path = (separator < 0 ? value : value.slice(0, separator)).trim()
  const label = (separator < 0 ? value : value.slice(separator + 1)).trim()
  if (!path) return false
  if (!silent) {
    const token = state.push('wikilink', 'a', 0)
    token.meta = { path, label: label || path }
  }
  state.pos = end + 2
  return true
})

markdown.renderer.rules.wikilink = (tokens, index) => {
  const { path, label } = tokens[index]!.meta as { path: string; label: string }
  return `<a href="#" data-vault-path="${markdown.utils.escapeHtml(path)}">${markdown.utils.escapeHtml(label)}</a>`
}

markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  const token = tokens[index]!
  const href = token.attrGet('href') ?? ''
  if (href.startsWith('vid2note://source/')) {
    try {
      const reference = new URL(href)
      const sourceId = decodeURIComponent(reference.pathname.slice(1))
      const start = Number(reference.searchParams.get('start'))
      const end = Number(reference.searchParams.get('end'))
      if (sourceId && Number.isInteger(start) && Number.isInteger(end) && start >= 0 && end > start) {
        token.attrSet('href', '#')
        token.attrSet('data-evidence-source', sourceId)
        token.attrSet('data-start-ms', String(start))
        token.attrSet('data-end-ms', String(end))
      }
    } catch {
      token.attrSet('href', '#')
    }
  } else if (/^https?:\/\//i.test(href)) {
    token.attrSet('data-external-link', 'true')
    token.attrSet('rel', 'noopener noreferrer')
  }
  return self.renderToken(tokens, index, options)
}

markdown.renderer.rules.heading_open = (tokens, index, _options, environment) => {
  const env = environment as RenderEnvironment
  const title = tokens[index + 1]?.content ?? ''
  const base = slug(title) || 'section'
  const count = (env.headingIds.get(base) ?? 0) + 1
  env.headingIds.set(base, count)
  const id = count === 1 ? base : `${base}-${count}`
  return `<${tokens[index]!.tag} id="${id}">`
}

const slug = (value: string): string =>
  value.normalize('NFKC').toLocaleLowerCase().replace(/[^\p{Letter}\p{Number}]+/gu, '-').replace(/^-|-$/g, '')

export function renderMarkdown(source: string): string {
  const rendered = markdown.render(source, { headingIds: new Map<string, number>() })
  return DOMPurify.sanitize(rendered, {
    ALLOWED_TAGS: ['a', 'blockquote', 'br', 'code', 'del', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'li', 'ol', 'p', 'pre', 'strong', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'ul'],
    ALLOWED_ATTR: ['class', 'data-evidence-source', 'data-end-ms', 'data-external-link', 'data-start-ms', 'data-vault-path', 'href', 'id', 'rel'],
    ALLOW_UNKNOWN_PROTOCOLS: false,
  })
}

export type OutlineHeading = { id: string; label: string; level: number }

export function extractOutline(source: string): OutlineHeading[] {
  const tokens = markdown.parse(source, {})
  const counts = new Map<string, number>()
  const headings: OutlineHeading[] = []
  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index]!
    if (token.type !== 'heading_open') continue
    const label = tokens[index + 1]?.content ?? ''
    const base = slug(label) || 'section'
    const count = (counts.get(base) ?? 0) + 1
    counts.set(base, count)
    headings.push({ id: count === 1 ? base : `${base}-${count}`, label, level: Number(token.tag.slice(1)) })
  }
  return headings
}
