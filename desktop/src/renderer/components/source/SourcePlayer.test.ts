import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SourcePlayer from './SourcePlayer.vue'

describe('SourcePlayer', () => {
  it('seeks relative to the rendered clip buffer', () => {
    const wrapper = mount(SourcePlayer, { props: { src: 'clip.mp4', startMs: 761000, endMs: 808000, mediaOffsetMs: 759500 } })
    expect(wrapper.get('video').element.currentTime).toBeCloseTo(1.5, 2)
  })

  it('shows a transcript fallback when media is unavailable', () => {
    expect(mount(SourcePlayer, { props: { startMs: 0, endMs: 1000 } }).text()).toContain('仅字幕证据')
  })
})
