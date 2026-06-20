import { describe, expect, it } from 'vitest'

import { extractOutline, renderMarkdown } from './renderMarkdown'

describe('renderMarkdown', () => {
  it('escapes raw HTML and preserves safe evidence links', () => {
    const html = renderMarkdown(
      '<script>alert(1)</script> [证据](vid2note://source/src_x?start=1000&end=2000)',
    )
    expect(html).not.toContain('<script')
    expect(html).toContain('data-evidence-source="src_x"')
    expect(html).toContain('data-start-ms="1000"')
  })

  it('renders wikilinks as interceptable vault links', () => {
    expect(renderMarkdown('[[wiki/topic.md|主题]]')).toContain('data-vault-path="wiki/topic.md"')
  })

  it('sanitizes unsafe links and gives duplicate headings stable ids', () => {
    const html = renderMarkdown('# Topic\n\n# Topic\n\n[x](javascript:alert(1))')
    expect(html).toContain('id="topic"')
    expect(html).toContain('id="topic-2"')
    expect(html).not.toContain('href="javascript:')
  })

  it('extracts an outline that targets the rendered heading ids', () => {
    expect(extractOutline('# Topic\n\n## Topic')).toEqual([
      { id: 'topic', label: 'Topic', level: 1 },
      { id: 'topic-2', label: 'Topic', level: 2 },
    ])
  })
})
