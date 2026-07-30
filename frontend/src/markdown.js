import DOMPurify from 'dompurify'
import { marked } from 'marked'

/**
 * Render LLM-generated Markdown without trusting embedded HTML.
 *
 * Markdown notes may contain local screenshot images, so regular HTML content
 * remains enabled while executable, form, frame, and inline-style surfaces are
 * removed.
 */
export function renderMarkdown(markdown) {
  const rendered = marked.parse(String(markdown ?? ''))
  const sanitized = DOMPurify.sanitize(rendered, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button'],
    FORBID_ATTR: ['style', 'srcdoc'],
    ALLOW_UNKNOWN_PROTOCOLS: false,
  })
  // PageHeader owns the page-level h1; note headings begin at h2.
  return sanitized.replace(/<(\/?)h([1-6])(\b[^>]*)>/gi, (_, closing, level, attributes) => {
    const shiftedLevel = Math.min(6, Number(level) + 1)
    return `<${closing}h${shiftedLevel}${attributes}>`
  })
}
