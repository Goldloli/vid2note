import { beforeEach, describe, expect, it, vi } from 'vitest'

const client = vi.hoisted(() => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
  fetchApiBlobUrl: vi.fn(),
}))

vi.mock('../client', () => client)

import { downloadArtifact } from '../task'

describe('protected artifact downloads', () => {
  beforeEach(() => vi.clearAllMocks())

  it('downloads through an authenticated Blob URL', async () => {
    client.fetchApiBlobUrl.mockResolvedValue('blob:artifact')
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    await downloadArtifact('task_000000000000', 'markdown_file')

    expect(client.fetchApiBlobUrl).toHaveBeenCalledWith(
      '/tasks/task_000000000000/artifacts/markdown_file',
    )
    expect(click).toHaveBeenCalledOnce()
  })
})
