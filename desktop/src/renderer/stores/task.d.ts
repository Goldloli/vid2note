export type TaskSummary = { id: string; status: string; [key: string]: unknown }

export const useTaskStore: () => {
  tasks: TaskSummary[]
  loadTasks(): Promise<void>
  addSrtTask(file: File): Promise<string>
}
