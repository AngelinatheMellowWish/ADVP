import { request } from './projects'

export type UpdateCheck = {
  available: boolean
  current: string
  latest: string | null
  notes_url: string | null
  downloads: Record<string, string>
  sha256: string | null
  checked_at?: string
}

export async function checkForUpdate(): Promise<UpdateCheck> {
  return request<UpdateCheck>('/api/updates/check', { method: 'POST' })
}
