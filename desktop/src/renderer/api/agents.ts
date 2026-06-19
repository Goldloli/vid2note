import { apiClient, getBaseURL } from './client'
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
  const source = new EventSource(
    `${await getBaseURL()}/agent/sessions/${encodeURIComponent(sessionId)}/events?after=${after}`,
  )
  source.onmessage = (message) => onEvent(JSON.parse(message.data) as AgentEvent)
  source.onerror = onError
  return () => source.close()
}
