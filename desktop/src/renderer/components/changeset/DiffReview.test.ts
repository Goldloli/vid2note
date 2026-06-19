import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DiffReview from './DiffReview.vue'

const changeset = {
  id: 'chg_000000000001',
  created_at: '2026-06-19T00:00:00Z',
  source_ids: ['src_1'],
  base_revision: 'base',
  agent_runtime: 'builtin',
  summary: '更新主题',
  operations: [
    { page_id: 'a', path: 'wiki/a.md', action: 'update', before: 'a', after: 'b', rationale: 'new', citations: [] },
    { page_id: 'b', path: 'wiki/b.md', action: 'create', before: null, after: 'c', rationale: 'new', citations: [] },
  ],
  contradictions: [],
  validation_result: { valid: true, issues: [] },
  status: 'pending',
} as const

describe('DiffReview', () => {
  it('submits only selected operation indexes', async () => {
    const wrapper = mount(DiffReview, { props: { changeset } })
    await wrapper.get('[data-operation-index="1"] input').setValue(false)
    await wrapper.get('[data-testid="approve-selected"]').trigger('click')
    expect(wrapper.emitted('approve')?.[0]).toEqual([[0]])
  })

  it('blocks apply while contradiction decisions are unresolved', () => {
    const wrapper = mount(DiffReview, { props: { changeset, blocked: true } })
    expect(wrapper.get('[data-testid="approve-selected"]').attributes('disabled')).toBeDefined()
  })
})
