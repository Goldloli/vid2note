import { describe, expect, it } from 'vitest'

import { renderMarkdown } from './renderMarkdown'

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
})
