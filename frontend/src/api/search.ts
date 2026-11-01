import { request } from './projects'

export type SearchHit = {
  kind: string
  object_id: string
  project_id: string | null
  title: string
  snippet: string
  url: string
}

export type SearchResponse = {
  query: string
  groups: Record<string, SearchHit[]>
  total: number
  raw_content_enabled: boolean
}

export async function searchAll(
  query: string,
  types?: string[],
  limit = 50,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  if (types && types.length > 0) params.set('types', types.join(','))
  return request<SearchResponse>(`/api/search?${params.toString()}`)
}
