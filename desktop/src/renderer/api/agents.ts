import { apiClient, getApiConnection } from './client'
import { consumeEventStream } from './eventStream'
import type { components } from './generated/schema'

export type AgentEvent = {
  run_id: string
  sequence: number
  type:
    | 'run.started'
    | 'thinking.delta'
    | 'message.delta'
    | 'tool.started'
    | 'tool.completed'
    | 'file.observed'
    | 'changeset.proposed'
    | 'approval.required'
    | 'usage'
    | 'run.completed'
    | 'run.failed'
    | 'run.cancelled'
  timestamp: string
  payload: Record<string, unknown>
}
export type AgentSession = components['schemas']['AgentSessionResponse']
export type AgentRun = components['schemas']['AgentRunResponse']
export type Runtime = components['schemas']['RuntimeResponse']

export const listRuntimes = (): Promise<Runtime[]> => apiClient.get('/agents')
export const listAgentSessions = (): Promise<AgentSession[]> => apiClient.get('/agent/sessions')
export const createAgentSession = (runtimeId: string, contextPaths: string[]): Promise<AgentSession> =>
  apiClient.post('/agent/sessions', { runtime_id: runtimeId, context_paths: contextPaths })
export const sendAgentMessage = (sessionId: string, message: string): Promise<AgentRun> =>
  apiClient.post(`/agent/sessions/${sessionId}/messages`, { message })
export const cancelAgentRun = (runId: string): Promise<unknown> =>
  apiClient.post(`/agent/runs/${runId}/cancel`)

export async function openAgentEventStream(
  sessionId: string,
  onEvent: (event: AgentEvent) => void,
  onError: () => void,
  after = 0,
): Promise<() => void> {
  const { baseURL, token } = await getApiConnection()
  const controller = new AbortController()
  void consumeEventStream(
    `${baseURL}/agent/sessions/${encodeURIComponent(sessionId)}/events?after=${after}`,
    token,
    controller.signal,
    (data) => onEvent(JSON.parse(data) as AgentEvent),
  ).catch(() => { if (!controller.signal.aborted) onError() })
  return () => controller.abort()
}
