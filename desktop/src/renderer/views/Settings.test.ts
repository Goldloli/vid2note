import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { storeApiKey, updateConfig } from '../api/config'
import Settings from './Settings.vue'

vi.mock('../api/config', () => ({
  getConfig: vi.fn().mockResolvedValue({ autonomy_mode: 'approval', workspace: { vault_path: '/notes', default_runtime: 'built-in', clip_buffer_ms: 1500 }, retention: {}, processing: {}, advanced: {}, asr: { provider: 'funasr' } }),
  updateConfig: vi.fn(),
  storeApiKey: vi.fn(),
  verifyApiKey: vi.fn(),
}))
vi.mock('../api/models', () => ({ listModels: vi.fn().mockResolvedValue({ llm_providers: ['qwen'] }) }))

describe('Settings', () => {
  it('explains approval mode, vault ownership and cloud data handling', async () => {
    const wrapper = mount(Settings, { global: { plugins: [createPinia()] } })
    await Promise.resolve()
    expect(wrapper.text()).toContain('审批模式')
    expect(wrapper.text()).toContain('Markdown Vault')
    expect(wrapper.text()).toContain('云数据说明')
  })

  it('saves workspace defaults and credentials through their typed controls', async () => {
    const wrapper = mount(Settings, { global: { plugins: [createPinia()] } })
    await flushPromises()
    await wrapper.get('[data-testid="vault-path"]').setValue('/knowledge')
    await wrapper.get('[data-testid="default-runtime"]').setValue('claude')
    await wrapper.get('[data-testid="clip-buffer-ms"]').setValue('2500')
    await wrapper.findAll('button').find((button) => button.text() === 'LLM 大模型')!.trigger('click')
    await wrapper.get('[data-testid="provider-api-key"]').setValue('secret-value')
    await wrapper.get('[data-testid="save-settings"]').trigger('click')
    await flushPromises()

    expect(updateConfig).toHaveBeenCalledWith(expect.objectContaining({
      vault_path: '/knowledge',
      default_runtime: 'claude',
      clip_buffer_ms: 2500,
    }))
    expect(storeApiKey).toHaveBeenCalledWith('qwen', 'secret-value')
    expect((wrapper.get('[data-testid="provider-api-key"]').element as HTMLInputElement).value).toBe('')
  })
})
