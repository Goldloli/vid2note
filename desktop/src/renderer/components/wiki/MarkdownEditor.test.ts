import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MarkdownEditor from './MarkdownEditor.vue'

describe('MarkdownEditor', () => {
  it('saves with the keyboard shortcut and exits with Escape', async () => {
    const wrapper = mount(MarkdownEditor, { props: { content: '# Before' } })
    await wrapper.get('textarea').setValue('# After')
    await wrapper.get('textarea').trigger('keydown', { key: 's', ctrlKey: true })
    await wrapper.get('textarea').trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('save')?.[0]).toEqual(['# After'])
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})
