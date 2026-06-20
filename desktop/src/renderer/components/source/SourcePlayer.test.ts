import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SourcePlayer from './SourcePlayer.vue'

describe('SourcePlayer', () => {
  it('seeks relative to the rendered clip buffer', () => {
    const wrapper = mount(SourcePlayer, { props: { src: 'clip.mp4', startMs: 761000, endMs: 808000, mediaOffsetMs: 759500 } })
    expect(wrapper.get('video').element.currentTime).toBeCloseTo(1.5, 2)
  })

  it('shows a transcript fallback with an explicit recovery action', async () => {
    const wrapper = mount(SourcePlayer, { props: { startMs: 0, endMs: 1000 } })
    expect(wrapper.text()).toContain('仅字幕证据')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('reacquire')).toHaveLength(1)
  })

  it('seeks when an asynchronously rendered clip becomes available', async () => {
    const wrapper = mount(SourcePlayer, {
      props: { startMs: 4000, endMs: 6000, mediaOffsetMs: 2500 },
    })

    await wrapper.setProps({ src: 'clip.mp4' })

    expect(wrapper.get('video').element.currentTime).toBeCloseTo(1.5, 2)
  })
})
