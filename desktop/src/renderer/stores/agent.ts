import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as api from '../api/agents'

export const useAgentStore = defineStore('agent', () => {
  const runtimes = ref<api.Runtime[]>([])
  const selectedRuntime = ref('built-in')
  const session = ref<api.AgentSession | null>(null)
  const sessions = ref<api.AgentSession[]>([])
  const run = ref<api.AgentRun | null>(null)
  const events = ref<api.AgentEvent[]>([])
  const lastError = ref<{ code: string; message?: string } | null>(null)
  let closeStream: (() => void) | null = null
  const running = computed(() => run.value?.status === 'running' && !events.value.some(isTerminal))
  async function refreshRuntimes(): Promise<void> {
    try {
      runtimes.value = await api.listRuntimes()
    } catch {
      lastError.value = { code: 'AGENT_RUNTIME_DETECTION_FAILED' }
    }
  }
  async function refreshSessions(): Promise<void> {
    try {
      sessions.value = await api.listAgentSessions()
    } catch {
      lastError.value = { code: 'AGENT_SESSION_LIST_FAILED' }
    }
  }
  async function start(contextPaths: string[] = []): Promise<void> {
    closeStream?.()
    events.value = []
    session.value = await api.createAgentSession(selectedRuntime.value, contextPaths)
    sessions.value = [session.value, ...sessions.value]
    closeStream = await api.openAgentEventStream(session.value.id, consume, () => {
      lastError.value = { code: 'AGENT_STREAM_ERROR' }
    })
  }
  async function send(message: string, contextPaths: string[] = []): Promise<void> {
    if (!session.value) await start(contextPaths)
    run.value = await api.sendAgentMessage(session.value!.id, message)
    if (!closeStream) {
      closeStream = await api.openAgentEventStream(session.value!.id, consume, () => {
        lastError.value = { code: 'AGENT_STREAM_ERROR' }
      }, events.value.length)
    }
  }
  function consume(event: api.AgentEvent): void {
    events.value.push(event)
    if (isTerminal(event)) {
      closeStream?.()
      closeStream = null
    }
    if (event.type === 'run.failed') {
      lastError.value = {
        code: String(event.payload.code ?? 'AGENT_FAILED'),
        message: typeof event.payload.message === 'string' ? event.payload.message : undefined,
      }
    }
  }
  async function cancel(): Promise<void> {
    if (run.value) await api.cancelAgentRun(run.value.id)
  }
  async function resume(selected: api.AgentSession): Promise<void> {
    closeStream?.()
    session.value = selected
    selectedRuntime.value = selected.runtime_id
    events.value = []
    closeStream = await api.openAgentEventStream(selected.id, consume, () => {
      lastError.value = { code: 'AGENT_STREAM_ERROR' }
    })
  }
  return { runtimes, selectedRuntime, session, sessions, run, events, lastError, running, refreshRuntimes, refreshSessions, start, send, consume, cancel, resume }
})

const isTerminal = (event: api.AgentEvent): boolean =>
  ['run.completed', 'run.failed', 'run.cancelled'].includes(event.type)
