import type { PipelineRun } from './pipelines'
import { request } from './projects'

export type TraceNode = {
  id: string
  key: string
  name: string
  position: number
  status: string
  attempts: number
  retries: number
  placeholder: boolean
  duration_ms: number
  started_at: string | null
  finished_at: string | null
  error: string | null
  output_summary: Record<string, unknown>
  provider_name: string | null
  model: string | null
  prompt_version: string | null
  selection_id: string | null
  input_tokens: number
  output_tokens: number
  estimated_cost: number
  currency: string
}

export type TraceLineage = {
  kind: string
  id: string
  name: string
  format: string
  row_count: number | null
  sha256: string | null
  sampled: boolean
}

export type TracePayload = {
  run: {
    id: string
    project_id: string
    dataset_id: string
    parent_run_id: string | null
    status: string
    current_step: string | null
    error: string | null
    created_at: string | null
    started_at: string | null
    finished_at: string | null
    duration_ms: number
  }
  summary: {
    node_count: number
    succeeded: number
    failed: number
    duration_ms: number
    selection_id: string | null
    chart_id: string | null
    provider_name: string | null
    model: string | null
    prompt_version: string | null
    input_tokens: number
    output_tokens: number
    estimated_cost: number
    currency: string
    retries: number
  }
  nodes: TraceNode[]
  edges: { from: string; to: string }[]
  lineage: TraceLineage[]
  artifacts: Record<string, string | null>
  app_version: string
}

export type RunComparisonStep = {
  key: string
  left: {
    status: string | null
    duration_ms: number
    attempts: number
    cost: number
    error: string | null
  }
  right: {
    status: string | null
    duration_ms: number
    attempts: number
    cost: number
    error: string | null
  }
  duration_delta_ms: number
  cost_delta: number
  changed: boolean
}

export type RunComparison = {
  left_run_id: string
  right_run_id: string
  left_status: string
  right_status: string
  left_duration_ms: number
  right_duration_ms: number
  left_cost: number
  right_cost: number
  changed: boolean
  steps: RunComparisonStep[]
}

export type CodeView = {
  selection_id: string
  language: string
  filename: string
  code: string
  parent_selection_id: string | null
  diff: string
  changed: boolean
}

export async function getTrace(runId: string): Promise<TracePayload> {
  return request<TracePayload>(`/api/pipeline-runs/${runId}/trace`)
}

export async function compareRuns(runId: string, otherId: string): Promise<RunComparison> {
  return request<RunComparison>(`/api/pipeline-runs/${runId}/compare/${otherId}`)
}

export async function rerunPipelineStep(runId: string, stepId: string): Promise<PipelineRun> {
  return request<PipelineRun>(`/api/pipeline-runs/${runId}/steps/${stepId}/rerun`, {
    method: 'POST',
  })
}

export async function getSelectionCode(selectionId: string): Promise<CodeView> {
  return request<CodeView>(`/api/chart-selections/${selectionId}/code`)
}
