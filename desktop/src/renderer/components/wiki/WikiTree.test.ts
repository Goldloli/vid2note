import { mount } from '@vue/test-utils'
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
})
