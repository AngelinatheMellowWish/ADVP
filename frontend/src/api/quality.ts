import { request } from './projects'
import type { CleanStep } from './cleaning'

export type QualityApplyResponse = {
  code: string
  steps: CleanStep[]
  columns: string[]
  affected_rows: number
  before_rows: number
  after_rows: number
  truncated: boolean
  preview: Record<string, unknown>[]
}

export async function applyQualitySuggestion(
  datasetId: string,
  code: string,
  column?: string | null,
): Promise<QualityApplyResponse> {
  return request<QualityApplyResponse>(`/api/datasets/${datasetId}/quality/apply`, {
    method: 'POST',
    body: JSON.stringify({ code, column: column ?? null }),
  })
}

export async function ignoreQualityIssue(
  datasetId: string,
  code: string,
): Promise<{ ignored_issues: string[] }> {
  return request<{ ignored_issues: string[] }>(
    `/api/datasets/${datasetId}/quality/ignore`,
    {
      method: 'POST',
      body: JSON.stringify({ code }),
    },
  )
}
