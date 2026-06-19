import { apiClient, getBaseURL } from './client'
import type { components } from './generated/schema'

type CreateTaskRequest = components['schemas']['CreateTaskRequest']
type TaskAcceptedResponse = components['schemas']['TaskAcceptedResponse']
type TaskListResponse = components['schemas']['TaskListResponse']
type TaskResponse = components['schemas']['TaskResponse']
type ArtifactListResponse = components['schemas']['ArtifactListResponse']

export const createTask = (
  videoUrl: string,
  opts: Partial<CreateTaskRequest> = {},
): Promise<TaskAcceptedResponse> =>
  apiClient.post<TaskAcceptedResponse, Partial<CreateTaskRequest>>('/tasks', {
    video_url: videoUrl,
    export_mindmap: opts.export_mindmap ?? true,
    ...opts,
  })

export const listTasks = (): Promise<TaskListResponse> => apiClient.get<TaskListResponse>('/tasks')

export const getTask = (taskId: string): Promise<TaskResponse> =>
  apiClient.get<TaskResponse>(`/tasks/${taskId}`)

export const rerunTask = (
  taskId: string,
  fromNode: string | null = null,
): Promise<TaskAcceptedResponse> =>
  apiClient.post<TaskAcceptedResponse, components['schemas']['RerunRequest']>(
    `/tasks/${taskId}/rerun`,
    { from_node: fromNode },
  )

export const listArtifacts = (taskId: string): Promise<ArtifactListResponse> =>
  apiClient.get<ArtifactListResponse>(`/tasks/${taskId}/artifacts`)

async function triggerDownload(path: string): Promise<void> {
  const link = document.createElement('a')
  link.href = `${await getBaseURL()}${path}`
  link.download = ''
  document.body.appendChild(link)
  link.click()
  link.remove()
}

export const downloadArtifact = (taskId: string, key: string): Promise<void> =>
  triggerDownload(`/tasks/${taskId}/artifacts/${key}`)

export const exportAllArtifacts = (taskId: string): Promise<void> =>
  triggerDownload(`/tasks/${taskId}/export`)
