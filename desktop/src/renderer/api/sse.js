export class TaskEventSource {
  constructor(taskId, onEvent, onError) {
    this.taskId = taskId
    this.onEvent = onEvent
    this.onError = onError
    this.es = null
    this.closed = false
  }

  async connect() {
    let baseURL = ''
    if (typeof window !== 'undefined' && window.electronAPI) {
      baseURL = await window.electronAPI.getBackendUrl()
    } else {
      baseURL = import.meta.env.VITE_API_BASE_URL || ''
    }
    const url = `${baseURL}/api/v1/tasks/${this.taskId}/events`
    this.es = new EventSource(url)

    this.es.onmessage = (event) => {
      if (event.data.startsWith(':keep-alive')) return
      try {
        const data = JSON.parse(event.data)
        this.onEvent(data)
      } catch (err) {
        console.error('Failed to parse SSE event:', err)
      }
    }

    this.es.onerror = (err) => {
      if (!this.closed && this.onError) {
        this.onError(err)
      }
    }
  }

  close() {
    this.closed = true
    if (this.es) {
      this.es.close()
      this.es = null
    }
  }
}
