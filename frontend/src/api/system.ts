import { request } from './projects'

export type SystemStatus = {
  service: string
  provider: string
  gpu: string
  disk_free_gb: number
  database: string
  cpu_percent: number
  memory_percent: number
  network_online: boolean | null
}

export function getSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return request<SystemStatus>('/api/system/status', { signal })
}
