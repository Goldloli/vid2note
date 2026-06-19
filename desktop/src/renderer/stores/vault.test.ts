import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, expect, it, vi } from 'vitest'

import { useVaultStore } from './vault'

const { listBacklinks, readVaultPage } = vi.hoisted(() => ({ listBacklinks: vi.fn(), readVaultPage: vi.fn() }))
vi.mock('../api/vault', async (original) => ({ ...(await original()), listBacklinks, readVaultPage }))

beforeEach(() => { setActivePinia(createPinia()); readVaultPage.mockReset(); listBacklinks.mockResolvedValue([]) })

it('does not replace the current page with a stale response', async () => {
  let resolveA!: (value: object) => void
  let resolveB!: (value: object) => void
  readVaultPage.mockImplementation((path: string) => new Promise((resolve) => {
    if (path === 'wiki/a.md') resolveA = resolve
    else resolveB = resolve
  }))
  const store = useVaultStore()
  const first = store.open('wiki/a.md')
  const second = store.open('wiki/b.md')
  resolveB({ path: 'wiki/b.md', content: 'B', content_hash: 'b', modified_at: '' })
  await second
  resolveA({ path: 'wiki/a.md', content: 'A', content_hash: 'a', modified_at: '' })
  await first
  expect(store.currentPage?.path).toBe('wiki/b.md')
})
