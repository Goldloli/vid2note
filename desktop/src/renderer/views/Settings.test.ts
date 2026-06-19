import { createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import Settings from './Settings.vue'

vi.mock('../api/config', () => ({
  getConfig: vi.fn().mockResolvedValue({ autonomy_mode: 'approval', retention: {}, processing: {}, advanced: {}, asr: { provider: 'funasr' } }),
  updateConfig: vi.fn(),
  verifyApiKey: vi.fn(),
}))
vi.mock('../api/models', () => ({ listModels: vi.fn().mockResolvedValue({ llm_providers: [] }) }))

describe('Settings', () => {
  it('explains approval mode, vault ownership and cloud data handling', async () => {
    const wrapper = mount(Settings, { global: { plugins: [createPinia()] } })
    await Promise.resolve()
    expect(wrapper.text()).toContain('审批模式')
    expect(wrapper.text()).toContain('Markdown Vault')
    expect(wrapper.text()).toContain('云数据说明')
  })
})
