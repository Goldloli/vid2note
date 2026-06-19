import { describe, expect, it } from 'vitest'

import { parseTaskEvent } from '../sse'

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
