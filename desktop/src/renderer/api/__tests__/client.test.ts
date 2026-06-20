import { afterEach, describe, expect, it, vi } from 'vitest'

describe('apiClient authentication', () => {
  afterEach(() => {
    delete window.electronAPI
    vi.resetModules()
  })

  it('adds the Electron session bearer token to API requests', async () => {
    window.electronAPI = {
      getBackendConnection: vi.fn().mockResolvedValue({
        baseUrl: 'http://127.0.0.1:18080',
        token: 'session-token',
      }),
      getBackendUrl: vi.fn(),
      chooseLocalVideo: vi.fn(),
      openExternal: vi.fn(),
    }
    const { apiClient } = await import('../client')
    let requestConfig: { baseURL?: string; headers?: Record<string, string> } | undefined

    await apiClient.get('/tasks', {
      adapter: async (config) => {
        requestConfig = config as typeof requestConfig
        return { data: [], status: 200, statusText: 'OK', headers: {}, config }
      },
    })

    expect(requestConfig?.baseURL).toBe('http://127.0.0.1:18080/api/v1')
    expect(requestConfig?.headers?.Authorization).toBe('Bearer session-token')
  })

  it('fetches protected assets with the bearer token and returns a Blob URL', async () => {
    window.electronAPI = {
      getBackendConnection: vi.fn().mockResolvedValue({
        baseUrl: 'http://127.0.0.1:18080',
        token: 'session-token',
      }),
      getBackendUrl: vi.fn(),
      chooseLocalVideo: vi.fn(),
      openExternal: vi.fn(),
    }
    const blob = new Blob(['media'])
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(blob, { status: 200, headers: { 'Content-Type': 'video/mp4' } }),
    )
    const createObjectURL = vi.fn().mockReturnValue('blob:protected-media')
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
    const { fetchApiBlobUrl } = await import('../client')

    const result = await fetchApiBlobUrl('/media/asset?path=clip.mp4')

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:18080/api/v1/media/asset?path=clip.mp4',
      { headers: { Authorization: 'Bearer session-token' } },
    )
    expect(createObjectURL).toHaveBeenCalledWith(expect.anything())
    expect(result).toBe('blob:protected-media')
  })
})
