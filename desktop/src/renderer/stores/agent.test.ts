import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAgentStore } from './agent'

vi.mock('../api/agents', () => ({
  listRuntimes: vi.fn().mockResolvedValue([
    { id: 'built-in', label: 'Built-in', detection: { available: true }, capabilities: {} },
    { id: 'claude', label: 'Claude', detection: { available: true }, capabilities: {} },
  ]),
}))
vi.mock('../api/config', () => ({
  getConfig: vi.fn().mockResolvedValue({ workspace: { default_runtime: 'claude' } }),
}))

describe('agent store defaults', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('hydrates the selected runtime from the shared config', async () => {
    const store = useAgentStore()
    await store.refreshRuntimes()
    expect(store.selectedRuntime).toBe('claude')
  })
})
