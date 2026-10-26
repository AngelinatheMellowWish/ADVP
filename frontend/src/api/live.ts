import { request } from './projects'

export type LiveStatus = 'connecting' | 'live' | 'paused' | 'reconnecting' | 'stopped' | 'error'

export type LiveSession = {
  session_id: string
  kind: 'websocket' | 'kafka'
  status: LiveStatus
  paused: boolean
  error: string | null
  sequence: number
  count: number
  records: Record<string, unknown>[]
  created_at: number
  updated_at: number
}

export type LiveSessionInput = {
  kind: 'websocket' | 'kafka'
  url?: string
  headers?: Record<string, string>
  bootstrap?: string
  topic?: string
  group?: string
  auto_offset_reset?: string
  security_protocol?: string
  sasl_mechanism?: string
  sasl_username?: string
  sasl_password?: string
  ssl_ca_location?: string
  max_messages?: number
  sample_interval_ms?: number
}

export async function createLiveSession(input: LiveSessionInput): Promise<LiveSession> {
  return request<LiveSession>('/api/streams/live', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function getLiveSession(sessionId: string): Promise<LiveSession> {
  return request<LiveSession>(`/api/streams/live/${sessionId}`)
}

export async function pauseLiveSession(sessionId: string): Promise<LiveSession> {
  return request<LiveSession>(`/api/streams/live/${sessionId}/pause`, { method: 'POST' })
}

export async function resumeLiveSession(sessionId: string): Promise<LiveSession> {
  return request<LiveSession>(`/api/streams/live/${sessionId}/resume`, { method: 'POST' })
}

export async function stopLiveSession(sessionId: string): Promise<LiveSession> {
  return request<LiveSession>(`/api/streams/live/${sessionId}/stop`, { method: 'POST' })
}

export async function saveLiveSnapshot(
  sessionId: string,
  projectId: string,
  name?: string,
): Promise<{ id: string; name: string; row_count: number }> {
  return request<{ id: string; name: string; row_count: number }>(
    `/api/streams/live/${sessionId}/snapshot`,
    {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, name: name || null }),
    },
  )
}
