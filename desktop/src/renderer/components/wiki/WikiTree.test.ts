import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'

import WikiTree from './WikiTree.vue'

describe('WikiTree', () => {
  it('renders raw collapsed and exposes pending count', () => {
    const wrapper = mount(WikiTree, {
      props: {
        tree: [
          { kind: 'file', name: 'index.md', path: 'index.md' },
          { kind: 'file', name: 'transcript.md', path: 'raw/src_1/transcript.md' },
        ],
        pendingCount: 3,
      },
    })
    expect(wrapper.get('[role="tree"]')).toBeTruthy()
    expect(wrapper.get('[data-path="raw"]').attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('[data-testid="pending-count"]').text()).toContain('3')
  })

  it('uses ArrowRight to expand and enter a directory without collapsing it', async () => {
    const wrapper = mount(WikiTree, {
      attachTo: document.body,
      props: {
        tree: [{ kind: 'file', name: 'transcript.md', path: 'raw/src_1/transcript.md' }],
        pendingCount: 0,
      },
    })
    const raw = wrapper.get('[data-path="raw"]')
    await raw.trigger('keydown', { key: 'ArrowRight' })
    expect(raw.attributes('aria-expanded')).toBe('true')

    await raw.trigger('keydown', { key: 'ArrowRight' })
    await nextTick()

    expect(document.activeElement?.getAttribute('data-path')).toBe('raw/src_1/transcript.md')
    expect(raw.attributes('aria-expanded')).toBe('true')
    wrapper.unmount()
  })
})
