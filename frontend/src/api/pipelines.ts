import type { CleanStep } from './cleaning'
import { request, type ChartIntent } from './projects'

export type PipelineStep = {
  id: string
  key: string
  name: string
  position: number
  status: string
  attempts: number
  placeholder: boolean
  output: Record<string, unknown>
  error: string | null
  started_at: string | null
  finished_at: string | null
}

export type PipelineRun = {
  id: string
  dataset_id: string
  project_id: string
  parent_run_id: string | null
  status: string
  current_step: string | null
  pause_requested: boolean
  cancel_requested: boolean
  options: Record<string, unknown>
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  steps: PipelineStep[]
}

export type PipelineRunSummary = {
  id: string
  dataset_id: string
  parent_run_id: string | null
  status: string
  current_step: string | null
  error: string | null
  created_at: string
  finished_at: string | null
}

export type CreatePipelineInput = {
  intent?: ChartIntent | null
  provider_id?: string | null
  max_reselects?: number
  clean_steps?: CleanStep[]
  confirm_high_risk?: boolean
  report_language?: 'zh' | 'en'
  report_template?: 'standard' | 'compact'
  report_conclusion?: string | null
  report_include_chart?: boolean
  auto_start?: boolean
}

export type ReportRegenerateInput = {
  language: 'zh' | 'en'
  template: 'standard' | 'compact'
  conclusion?: string | null
  include_chart?: boolean
}

export type ReportRegenerateResponse = {
  run: PipelineRun
  report: {
    markdown: string
    html: string
    pdf: string
    [key: string]: unknown
  }
}

export async function createPipelineRun(
  datasetId: string,
  input: CreatePipelineInput = {},
): Promise<PipelineRun> {
  return request<PipelineRun>(`/api/datasets/${datasetId}/pipeline-runs`, {
    method: 'POST',
    body: JSON.stringify({
      intent: input.intent ?? null,
      provider_id: input.provider_id ?? null,
      max_reselects: input.max_reselects ?? 2,
      clean_steps: input.clean_steps ?? [],
      confirm_high_risk: input.confirm_high_risk ?? false,
      report_language: input.report_language ?? 'zh',
      report_template: input.report_template ?? 'standard',
      report_conclusion: input.report_conclusion ?? null,
      report_include_chart: input.report_include_chart ?? true,
      auto_start: input.auto_start ?? true,
    }),
  })
}

export async function regeneratePipelineReport(
  runId: string,
  input: ReportRegenerateInput,
): Promise<ReportRegenerateResponse> {
  return request<ReportRegenerateResponse>(`/api/pipeline-runs/${runId}/report`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function listPipelineRuns(
  datasetId: string,
  limit = 20,
): Promise<PipelineRunSummary[]> {
  return request<PipelineRunSummary[]>(
    `/api/datasets/${datasetId}/pipeline-runs?limit=${limit}`,
  )
}

export async function getPipelineRun(runId: string): Promise<PipelineRun> {
  return request<PipelineRun>(`/api/pipeline-runs/${runId}`)
}

export async function pausePipelineRun(runId: string): Promise<PipelineRun> {
  return request<PipelineRun>(`/api/pipeline-runs/${runId}/pause`, { method: 'POST' })
}

export async function resumePipelineRun(runId: string): Promise<PipelineRun> {
  return request<PipelineRun>(`/api/pipeline-runs/${runId}/resume`, { method: 'POST' })
}

export async function cancelPipelineRun(runId: string): Promise<PipelineRun> {
  return request<PipelineRun>(`/api/pipeline-runs/${runId}/cancel`, { method: 'POST' })
}

export async function retryPipelineStep(
  runId: string,
  stepId: string,
): Promise<PipelineRun> {
  return request<PipelineRun>(`/api/pipeline-runs/${runId}/steps/${stepId}/retry`, {
    method: 'POST',
  })
}
