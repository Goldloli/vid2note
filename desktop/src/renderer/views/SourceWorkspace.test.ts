import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

const mediaApi = vi.hoisted(() => ({ getClip: vi.fn(), getMediaAssetUrl: vi.fn() }))
const vaultApi = vi.hoisted(() => ({ readSource: vi.fn(), readVaultPage: vi.fn() }))
vi.mock('../api/media', () => mediaApi)
vi.mock('../api/vault', () => vaultApi)
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import SourcePlayer from '../components/source/SourcePlayer.vue'
import SourceTimeline from '../components/source/SourceTimeline.vue'
import SourceWorkspace from './SourceWorkspace.vue'

describe('SourceWorkspace', () => {
  it('does not let an older clip request replace a newer evidence range', async () => {
    let finishOld!: (value: unknown) => void
    let finishNew!: (value: unknown) => void
    mediaApi.getClip
      .mockResolvedValueOnce({ asset_path: 'initial.mp4', rendered_start_ms: 0 })
      .mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve }))
      .mockReturnValueOnce(new Promise((resolve) => { finishNew = resolve }))
    mediaApi.getMediaAssetUrl.mockImplementation(async (path: string) => `blob:${path}`)
    vaultApi.readSource.mockResolvedValue({ title: 'Source', duration_ms: 60_000 })
    vaultApi.readVaultPage.mockResolvedValue({ content: '' })
    vi.stubGlobal('URL', { revokeObjectURL: vi.fn() })
    const wrapper = mount(SourceWorkspace, {
      props: { sourceId: 'src_1' },
      global: { stubs: { RouterLink: true } },
    })
    await flushPromises()

    const timeline = wrapper.findComponent(SourceTimeline)
    timeline.vm.$emit('seek', { id: 'old', startMs: 1_000, endMs: 2_000, text: 'old' })
    timeline.vm.$emit('seek', { id: 'new', startMs: 3_000, endMs: 4_000, text: 'new' })
    finishNew({ asset_path: 'new.mp4', rendered_start_ms: 3_000 })
    await flushPromises()
    finishOld({ asset_path: 'old.mp4', rendered_start_ms: 1_000 })
    await flushPromises()

    expect(wrapper.findComponent(SourcePlayer).props('src')).toBe('blob:new.mp4')
    expect(wrapper.findComponent(SourcePlayer).props('mediaOffsetMs')).toBe(3_000)
  })
})
