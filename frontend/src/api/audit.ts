import { request } from './projects'

export type AuditEvent = {
  id: string
  project_id: string | null
  event: string
  target_type: string | null
  target_id: string | null
  detail: Record<string, unknown>
  created_at: string | null
}

export type AuditFilters = {
  projectId?: string | null
  event?: string
  target?: string
  keyword?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
}

export function auditQuery(filters: AuditFilters): string {
  const params = new URLSearchParams()
  if (filters.projectId) params.set('project_id', filters.projectId)
  if (filters.event?.trim()) params.set('event', filters.event.trim())
  if (filters.target?.trim()) params.set('target', filters.target.trim())
  if (filters.keyword?.trim()) params.set('q', filters.keyword.trim())
  if (filters.since?.trim()) params.set('since', filters.since.trim())
  if (filters.until?.trim()) params.set('until', filters.until.trim())
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))
  if (filters.offset !== undefined) params.set('offset', String(filters.offset))
  return params.toString()
}

export async function listAuditEvents(filters: AuditFilters): Promise<AuditEvent[]> {
  const query = auditQuery(filters)
  return request<AuditEvent[]>(`/api/audit/events${query ? `?${query}` : ''}`)
}

export function auditExportUrl(format: 'json' | 'csv', filters: AuditFilters): string {
  const query = auditQuery(filters)
  return `/api/audit/export${query ? `?${query}&` : '?'}format=${format}`
}
