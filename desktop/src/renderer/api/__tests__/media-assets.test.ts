import { beforeEach, describe, expect, it, vi } from 'vitest'

const client = vi.hoisted(() => ({
  apiClient: { get: vi.fn() },
  fetchApiBlobUrl: vi.fn(),
}))

vi.mock('../client', () => client)

import { getMediaAssetUrl } from '../media'

describe('media assets', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads generated media through the authenticated Blob helper', async () => {
    client.fetchApiBlobUrl.mockResolvedValue('blob:clip')

    await expect(getMediaAssetUrl('.vid2note/cache/clips/clip.mp4')).resolves.toBe('blob:clip')

    expect(client.fetchApiBlobUrl).toHaveBeenCalledWith(
      '/media/asset?path=.vid2note%2Fcache%2Fclips%2Fclip.mp4',
    )
  })
})
