import type { components } from './generated/schema'
import { getApiConnection } from './client'
import { consumeEventStream } from './eventStream'

export type TaskEvent = components['schemas']['TaskEvent']

const EVENT_TYPES = new Set<TaskEvent['event_type']>([
  'task.created',
  'task.started',
  'task.retrying',
  'task.rerun',
  'task.completed',
  'task.failed',
  'task.interrupted',
  'node.started',
  'node.completed',
  'node.failed',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export function parseTaskEvent(value: unknown): TaskEvent | null {
  if (!isRecord(value)) return null
  if (
    typeof value.task_id !== 'string' ||
    typeof value.event_type !== 'string' ||
    !EVENT_TYPES.has(value.event_type as TaskEvent['event_type']) ||
    typeof value.progress !== 'number' ||
    value.progress < 0 ||
    value.progress > 100 ||
    typeof value.timestamp !== 'string'
  ) {
    return null
  }
  if (value.event_type === 'task.completed' && value.progress !== 100) return null
  if (
    (value.event_type === 'task.failed' || value.event_type === 'task.interrupted') &&
    typeof value.message !== 'string'
  ) {
    return null
  }
  return value as TaskEvent
}

export class TaskEventSource {
  private controller: AbortController | null = null
  private closed = false

  constructor(
    private readonly taskId: string,
    private readonly onEvent: (event: TaskEvent) => void,
    private readonly onError?: (event: Event) => void,
  ) {}

  async connect(): Promise<void> {
    const { baseURL, token } = await getApiConnection()
    this.controller = new AbortController()
    void consumeEventStream(`${baseURL}/tasks/${this.taskId}/events`, token, this.controller.signal, (data) => {
      try {
        const parsed = parseTaskEvent(JSON.parse(data) as unknown)
        if (parsed) this.onEvent(parsed)
      } catch (error) {
        console.error('Failed to parse SSE event:', error)
      }
    }).catch(() => { if (!this.closed) this.onError?.(new Event('error')) })
  }

  close(): void {
    this.closed = true
    this.controller?.abort()
    this.controller = null
  }
}
