import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

describe('workspace tokens', () => {
  it('exposes the workspace color and spacing contract', () => {
    const path = resolve(process.cwd(), 'src/renderer/styles/tokens.css')
    const css = readFileSync(path, 'utf8')

    expect(css).toContain('--color-accent: #2383e2')
    expect(css).toContain('--rail-width: 52px')
    expect(css).toContain('--focus-ring')
    expect(css).toContain('prefers-reduced-motion: reduce')
  })
})
