import { request } from './projects'

export type TrameSession = {
  id: string
  scene_id: string
  dataset_id: string
  url: string
  port: number
  created_at: number
  updated_at: number
}

export async function startTrame(sceneId: string): Promise<TrameSession> {
  return request<TrameSession>(`/api/scenes/${sceneId}/trame`, { method: 'POST' })
}

export async function getTrame(sessionId: string): Promise<TrameSession> {
  return request<TrameSession>(`/api/trame/${sessionId}`)
}

export async function stopTrame(sessionId: string): Promise<{ stopped: boolean }> {
  return request<{ stopped: boolean }>(`/api/trame/${sessionId}`, { method: 'DELETE' })
}
