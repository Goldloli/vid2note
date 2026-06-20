import { afterEach, expect, it, vi } from 'vitest'

afterEach(() => {
  delete window.electronAPI
  vi.unstubAllGlobals()
  vi.resetModules()
})

it('authenticates agent SSE with a fetch stream', async () => {
  window.electronAPI = {
    getBackendConnection: vi.fn().mockResolvedValue({
      baseUrl: 'http://127.0.0.1:18080',
      token: 'session-token',
    }),
    getBackendUrl: vi.fn(),
    chooseLocalVideo: vi.fn(),
    openExternal: vi.fn(),
  }
  const event = { run_id: 'run-1', sequence: 0, type: 'run.started', timestamp: 'now', payload: {} }
  const reader = {
    read: vi.fn()
      .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`) })
      .mockResolvedValueOnce({ done: true, value: undefined }),
  }
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, body: { getReader: () => reader } })
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('EventSource', vi.fn(() => { throw new Error('EventSource must not be used') }))
  const onEvent = vi.fn()
  const { openAgentEventStream } = await import('../agents')

  const close = await openAgentEventStream('session-1', onEvent, vi.fn())
  await vi.waitFor(() => expect(onEvent).toHaveBeenCalledWith(event))

  expect(fetchMock).toHaveBeenCalledWith(
    'http://127.0.0.1:18080/api/v1/agent/sessions/session-1/events?after=0',
    expect.objectContaining({ headers: { Authorization: 'Bearer session-token' } }),
  )
  close()
})
