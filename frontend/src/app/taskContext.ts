import { createContext, useContext } from 'react'

export type TaskCounts = {
  imports: number
  pipelines: number
  exports: number
  render_jobs: number
  live_streams: number
}

export type TaskContextValue = {
  tasks: TaskCounts
  total: number
  error: boolean
  refresh: () => void
}

export const TaskContext = createContext<TaskContextValue | null>(null)

export function useTasks(): TaskContextValue {
  const value = useContext(TaskContext)
  if (!value) {
    throw new Error('useTasks must be used within TaskProvider')
  }
  return value
}
