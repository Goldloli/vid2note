import { afterEach, describe, expect, it, vi } from 'vitest'

import { parseTaskEvent, TaskEventSource } from '../sse'

const baseEvent = {
  task_id: 'task_0123456789ab',
  progress: 100,
  timestamp: '2026-06-19T09:00:00Z',
}

describe('parseTaskEvent', () => {
  it('accepts a complete terminal event', () => {
    expect(parseTaskEvent({ ...baseEvent, event_type: 'task.completed' })).not.toBeNull()
  })

  it('rejects terminal failures without a user-facing message', () => {
    expect(
      parseTaskEvent({ ...baseEvent, event_type: 'task.failed', progress: 0 }),
    ).toBeNull()
  })
})

describe('TaskEventSource authentication', () => {
  afterEach(() => {
    delete window.electronAPI
    vi.unstubAllGlobals()
  })

  it('uses an authenticated fetch stream instead of EventSource', async () => {
    window.electronAPI = {
      getBackendConnection: vi.fn().mockResolvedValue({
        baseUrl: 'http://127.0.0.1:18080',
        token: 'session-token',
      }),
      getBackendUrl: vi.fn(),
      chooseLocalVideo: vi.fn(),
      openExternal: vi.fn(),
    }
    const payload = JSON.stringify({ ...baseEvent, event_type: 'task.completed' })
    const reader = {
      read: vi.fn()
        .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode(`data: ${payload}\n\n`) })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, body: { getReader: () => reader } })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('EventSource', vi.fn(() => { throw new Error('EventSource must not be used') }))
    const received = vi.fn()

    const source = new TaskEventSource('task_0123456789ab', received)
    await source.connect()
    await vi.waitFor(() => expect(received).toHaveBeenCalledOnce())

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:18080/api/v1/tasks/task_0123456789ab/events',
      expect.objectContaining({ headers: { Authorization: 'Bearer session-token' } }),
    )
    source.close()
  })
})
