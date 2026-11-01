import { request } from './projects'

export type ActiveTaskCounts = {
  pipelines: number
  exports: number
  render_jobs: number
  live_streams: number
  total: number
}

export type LifecycleState = {
  shutdown_enabled: boolean
  mode: string
  active_tasks: ActiveTaskCounts
}

export type ShutdownResult = {
  status: string
  active_tasks: ActiveTaskCounts
}

export async function getLifecycle(): Promise<LifecycleState> {
  return request<LifecycleState>('/api/system/lifecycle')
}

export async function shutdownService(force = false): Promise<ShutdownResult> {
  return request<ShutdownResult>('/api/system/shutdown', {
    method: 'POST',
    body: JSON.stringify({ force }),
  })
}
