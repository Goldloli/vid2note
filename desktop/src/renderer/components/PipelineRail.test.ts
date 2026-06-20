import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import PipelineRail from './PipelineRail.vue'

describe('PipelineRail recovery state', () => {
  it('shows interrupted tasks as interrupted instead of failed or completed', () => {
    const wrapper = mount(PipelineRail, {
      props: { status: 'interrupted', progress: 45, title: 'Recovered task' },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })

    expect(wrapper.text()).toContain('已中断')
    expect(wrapper.text()).not.toContain('已完成')
    expect(wrapper.find('.badge').classes()).toContain('warn')
  })
})
