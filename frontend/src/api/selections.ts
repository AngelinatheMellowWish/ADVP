import { request, type ChartIntent } from './projects'

export type SelectedChartInfo = {
  chart_id: string
  name: { zh: string; en: string }
  family: string
  backend: string
  fields: Record<string, string>
  aggregation: string | null
  reason: string
  confidence: number | null
  style?: Record<string, unknown> | null
  score: number
  dimensions: Record<string, number>
}

export type SelectionTop3Entry = {
  chart_id: string
  name: { zh: string; en: string }
  score: number
  selected: boolean
  reason: string
}

export type ChartSelectionResult = {
  id: string
  dataset_id: string
  project_id: string
  provider_id: string | null
  provider_name: string | null
  model: string | null
  prompt_version: string
  intent: string | null
  selected: SelectedChartInfo
  top3: SelectionTop3Entry[]
  attempts: number
  reselects: number
  degraded: boolean
  degradation_reason: string | null
  needs_confirmation: boolean
  budget?: {
    project_limit: number | null
    monthly_limit: number | null
    project_spend: number
    monthly_spend: number
    warning_ratio: number
    currency: string
    warning: boolean
    exceeded: boolean
    reason: string | null
  } | null
  parent_selection_id?: string | null
  correction_instruction?: string | null
  usage: {
    input_tokens: number
    output_tokens: number
    cached_tokens: number
    estimated_cost: number
    currency: string
  }
  created_at: string
}

export type ChartSelectionSummary = {
  id: string
  dataset_id: string
  selected_chart_id: string
  score: number
  degraded: boolean
  needs_confirmation: boolean
  provider_name: string | null
  created_at: string
}

export async function createChartSelection(
  datasetId: string,
  input: { intent?: ChartIntent | null; provider_id?: string | null; max_reselects?: number } = {},
): Promise<ChartSelectionResult> {
  return request<ChartSelectionResult>(`/api/datasets/${datasetId}/chart-selection`, {
    method: 'POST',
    body: JSON.stringify({
      intent: input.intent ?? null,
      provider_id: input.provider_id ?? null,
      max_reselects: input.max_reselects ?? 2,
    }),
  })
}

export async function listChartSelections(
  datasetId: string,
  limit = 20,
): Promise<ChartSelectionSummary[]> {
  return request<ChartSelectionSummary[]>(
    `/api/datasets/${datasetId}/chart-selections?limit=${limit}`,
  )
}

export async function getChartSelection(selectionId: string): Promise<ChartSelectionResult> {
  return request<ChartSelectionResult>(`/api/chart-selections/${selectionId}`)
}

export type ChartRenderer = 'plotly' | 'echarts' | 'cytoscape' | 'deckgl' | 'vtk'

export type ChartFigureResponse = {
  selection_id: string
  dataset_id: string
  chart_id: string
  renderer: ChartRenderer
  figure: {
    data?: unknown[]
    layout?: Record<string, unknown>
    frames?: unknown[]
    option?: Record<string, unknown>
    elements?: Record<string, unknown>
    layers?: unknown[]
    viewState?: Record<string, unknown>
    imaging?: Record<string, unknown>
    [key: string]: unknown
  }
  row_count: number
  sampled: boolean
  max_rows: number
}

export async function correctChartSelection(
  selectionId: string,
  instruction: string,
  providerId?: string | null,
): Promise<ChartSelectionResult> {
  return request<ChartSelectionResult>(`/api/chart-selections/${selectionId}/correct`, {
    method: 'POST',
    body: JSON.stringify({
      instruction,
      provider_id: providerId ?? null,
    }),
  })
}

export async function getChartFigure(selectionId: string): Promise<ChartFigureResponse> {
  return request<ChartFigureResponse>(`/api/chart-selections/${selectionId}/figure`)
}
