import type { components } from './generated/schema'

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
  private eventSource: EventSource | null = null
  private closed = false

  constructor(
    private readonly taskId: string,
    private readonly onEvent: (event: TaskEvent) => void,
    private readonly onError?: (event: Event) => void,
  ) {}

  async connect(): Promise<void> {
    let baseURL = ''
    if (typeof window !== 'undefined' && window.electronAPI) {
      baseURL = await window.electronAPI.getBackendUrl()
    } else {
      baseURL = import.meta.env.VITE_API_BASE_URL || ''
    }
    const apiBase = baseURL.endsWith('/api/v1') ? baseURL : `${baseURL}/api/v1`
    this.eventSource = new EventSource(`${apiBase}/tasks/${this.taskId}/events`)
    this.eventSource.onmessage = (event) => {
      try {
        const parsed = parseTaskEvent(JSON.parse(event.data) as unknown)
        if (parsed) this.onEvent(parsed)
      } catch (error) {
        console.error('Failed to parse SSE event:', error)
      }
    }
    this.eventSource.onerror = (event) => {
      if (!this.closed) this.onError?.(event)
    }
  }

  close(): void {
    this.closed = true
    this.eventSource?.close()
    this.eventSource = null
  }
}
