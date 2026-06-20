import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SourceTimeline from './SourceTimeline.vue'

describe('SourceTimeline', () => {
  it('virtualizes long transcripts and keeps the active segment available', () => {
    const segments = Array.from({ length: 10_000 }, (_, index) => ({
      id: `seg-${index}`,
      startMs: index * 1000,
      endMs: (index + 1) * 1000,
      text: `Segment ${index}`,
    }))
    const wrapper = mount(SourceTimeline, { props: { segments, activeId: 'seg-8765' } })

    expect(wrapper.findAll('li').length).toBeLessThan(100)
    expect(wrapper.get('[data-segment-id="seg-8765"]').attributes('aria-current')).toBe('true')
  })
})
