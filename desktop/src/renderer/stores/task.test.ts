import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const taskApi = vi.hoisted(() => ({
  listTasks: vi.fn(),
  createTask: vi.fn(),
}))
const processApi = vi.hoisted(() => ({
  uploadSrt: vi.fn(),
  startProcess: vi.fn(),
}))
const streamCallbacks = vi.hoisted(() => [] as Array<(event: Record<string, unknown>) => void>)
const closedStreams = vi.hoisted(() => [] as string[])

vi.mock('../api/task', () => taskApi)
vi.mock('../api/process', () => processApi)
vi.mock('../api/sse', () => ({
  TaskEventSource: class {
    taskId: string
    constructor(taskId: string, onEvent: (event: Record<string, unknown>) => void) {
      this.taskId = taskId
      streamCallbacks.push(onEvent)
    }
    connect() {}
    close() { closedStreams.push(this.taskId) }
  },
}))

import { useTaskStore } from './task'

describe('task store loading', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    streamCallbacks.length = 0
    closedStreams.length = 0
  })

  it('keeps a task created while an older list request is in flight', async () => {
    let finishList!: (value: unknown) => void
    taskApi.listTasks.mockReturnValue(new Promise((resolve) => { finishList = resolve }))
    processApi.uploadSrt.mockResolvedValue({ file_id: 'upload-2.srt', filename: 'topic.srt' })
    processApi.startProcess.mockResolvedValue({ task_id: 'task-2' })

    const store = useTaskStore()
    const loading = store.loadTasks()
    await store.addSrtTask(new File(['subtitle'], 'topic.srt'))
    finishList({ tasks: [{ id: 'task-1', status: 'completed' }], total: 1 })
    await loading

    expect(store.tasks.map((task) => task.id)).toEqual(['task-2', 'task-1'])
  })

  it('keeps a terminal SSE update when an older list response has the same task id', async () => {
    processApi.uploadSrt.mockResolvedValue({ file_id: 'upload-2.srt', filename: 'topic.srt' })
    processApi.startProcess.mockResolvedValue({ task_id: 'task-2' })
    const store = useTaskStore()
    await store.addSrtTask(new File(['subtitle'], 'topic.srt'))

    let finishList!: (value: unknown) => void
    taskApi.listTasks.mockReturnValue(new Promise((resolve) => { finishList = resolve }))
    const loading = store.loadTasks()
    streamCallbacks[0]!({ event_type: 'task.completed', progress: 100 })
    finishList({ tasks: [{ id: 'task-2', status: 'pending', progress: 0 }], total: 1 })
    await loading

    expect(store.tasks[0]?.status).toBe('completed')
    expect(store.tasks[0]?.progress).toBe(100)
  })

  it('removes a stale local task when the current list response no longer contains it', async () => {
    taskApi.listTasks
      .mockResolvedValueOnce({ tasks: [{ id: 'task-1', status: 'completed' }], total: 1 })
      .mockResolvedValueOnce({ tasks: [], total: 0 })
    const store = useTaskStore()

    await store.loadTasks()
    await store.loadTasks()

    expect(store.tasks).toEqual([])
  })

  it('ignores an older list request that resolves after a newer request', async () => {
    let finishOld!: (value: unknown) => void
    let finishNew!: (value: unknown) => void
    taskApi.listTasks
      .mockReturnValueOnce(new Promise((resolve) => { finishOld = resolve }))
      .mockReturnValueOnce(new Promise((resolve) => { finishNew = resolve }))
    const store = useTaskStore()

    const oldLoad = store.loadTasks()
    const newLoad = store.loadTasks()
    finishNew({ tasks: [{ id: 'task-1', status: 'completed' }], total: 1 })
    await newLoad
    finishOld({ tasks: [{ id: 'task-1', status: 'pending' }], total: 1 })
    await oldLoad

    expect(store.tasks[0]?.status).toBe('completed')
  })

  it('marks an interrupted task terminal and closes its event stream', async () => {
    processApi.uploadSrt.mockResolvedValue({ file_id: 'upload-2.srt', filename: 'topic.srt' })
    processApi.startProcess.mockResolvedValue({ task_id: 'task-2' })
    const store = useTaskStore()
    await store.addSrtTask(new File(['subtitle'], 'topic.srt'))

    streamCallbacks[0]!({ event_type: 'task.interrupted', progress: 45 })

    expect(store.tasks[0]?.status).toBe('interrupted')
    expect(closedStreams).toContain('task-2')
  })
})
