const escapeHtml = (value: string): string =>
  value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]!)

const safePath = (value: string): string => value.replace(/[\u0000-\u001f"'<>]/g, '')

export function renderMarkdown(markdown: string): string {
  const anchors: string[] = []
  const token = (html: string): string => {
    const index = anchors.push(html) - 1
    return `VID2NOTEANCHOR${index}END`
  }
  let source = markdown.replace(
    /\[([^\]]+)]\(vid2note:\/\/source\/([^?\s)]+)\?start=(\d+)&end=(\d+)\)/g,
    (_match, label: string, sourceId: string, start: string, end: string) => token(
      `<a href="#" data-evidence-source="${escapeHtml(safePath(sourceId))}" data-start-ms="${start}" data-end-ms="${end}">${escapeHtml(label)}</a>`,
    ),
  )
  source = source.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?]]/g, (_match, path: string, label?: string) =>
    token(`<a href="#" data-vault-path="${escapeHtml(safePath(path))}">${escapeHtml(label ?? path)}</a>`),
  )
  source = escapeHtml(source)
  source = source
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" data-external-link="true">$1</a>')
    .split(/\n{2,}/)
    .map((block) => (/^<(?:h[1-3]|ul|ol|pre)/.test(block) ? block : `<p>${block.replace(/\n/g, '<br>')}</p>`))
    .join('\n')
  return source.replace(/VID2NOTEANCHOR(\d+)END/g, (_match, index: string) => anchors[Number(index)] ?? '')
}
