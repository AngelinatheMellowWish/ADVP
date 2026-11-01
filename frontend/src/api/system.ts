import { request } from './projects'

export type ProviderStatus = {
  status: string
  name: string | null
  has_key: boolean
}

export type SystemStatus = {
  service: string
  provider: string | ProviderStatus
  gpu: string
  disk_free_gb: number
  database: string
  cpu_percent: number
  memory_percent: number
  network_online: boolean | null
  active_tasks?: Record<string, number>
}

export function getSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return request<SystemStatus>('/api/system/status', { signal })
}
