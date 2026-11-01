import { request } from './projects'

export type CleanOperation =
  | 'drop_missing'
  | 'fill_missing'
  | 'clip_outliers'
  | 'deduplicate'
  | 'cast_type'
  | 'rename_columns'
  | 'drop_columns'

export type CleanStep = {
  operation: CleanOperation
  columns?: string[]
  column?: string
  strategy?: string
  value?: unknown
  method?: string
  factor?: number
  subset?: string[]
  mapping?: Record<string, string>
  target?: string
}

export type CleanLogEntry = {
  step: number
  operation: string
  affected_rows: number
  before_rows?: number
  after_rows?: number
  before_nulls_total?: number
  after_nulls_total?: number
  columns?: string[]
  column?: string
  strategy?: string
  method?: string
  target?: string
  mapping?: Record<string, string>
  bounds?: Record<string, number>
}

export type CleanResponse = {
  source_dataset_id: string
  derived_dataset_id: string | null
  cleaning_run_id: string | null
  dry_run: boolean
  before_rows: number
  after_rows: number
  truncated: boolean
  log: CleanLogEntry[]
  preview: Record<string, unknown>[]
}

export type CleaningSummary = {
  id: string
  dataset_id: string
  derived_dataset_id: string | null
  parent_run_id: string | null
  before_rows: number
  after_rows: number
  truncated: boolean
  created_at: string
}

export type CleanUndoResponse = {
  dataset_id: string
  cleaning_run_id: string | null
  message: string
}

export async function cleanDataset(
  datasetId: string,
  steps: CleanStep[],
  options: { dryRun?: boolean; confirmHighRisk?: boolean } = {},
): Promise<CleanResponse> {
  return request<CleanResponse>(`/api/datasets/${datasetId}/clean`, {
    method: 'POST',
    body: JSON.stringify({
      steps,
      dry_run: options.dryRun ?? false,
      confirm_high_risk: options.confirmHighRisk ?? false,
    }),
  })
}

export async function listCleanings(datasetId: string): Promise<CleaningSummary[]> {
  return request<CleaningSummary[]>(`/api/datasets/${datasetId}/cleanings`)
}

export async function undoCleaning(runId: string): Promise<CleanUndoResponse> {
  return request<CleanUndoResponse>(`/api/cleanings/${runId}/undo`, { method: 'POST' })
}

export async function rollbackCleaning(runId: string): Promise<CleanUndoResponse> {
  return request<CleanUndoResponse>(`/api/cleanings/${runId}/rollback`, { method: 'POST' })
}
