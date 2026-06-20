import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ContradictionPanel from './ContradictionPanel.vue'

describe('ContradictionPanel', () => {
  it('requires an explicit choice', async () => {
    const wrapper = mount(ContradictionPanel, { props: { contradiction: { topic: '事实', claim_a: 'A', claim_b: 'B' } } })
    await wrapper.get('[data-testid="confirm-contradiction"]').trigger('click')
    expect(wrapper.text()).toContain('请选择处理方式')
  })
})
