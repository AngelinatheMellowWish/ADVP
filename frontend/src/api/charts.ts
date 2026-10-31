import { request } from './projects'
import type { ChartSelectionResult } from './selections'

export type ChartRegistryEntry = {
  id: string
  name: { zh: string; en: string }
  family: string
  backend: string
  dataKinds: string[]
  requiredTypes: Record<string, string>
  optional: string[]
  maxRows: number
  maxCardinality: Record<string, number>
  constraints: { minNumericFields?: number; minRows?: number }
  intents: string[]
  supports: string[]
  perceptualScore?: number
  accessibilityNotes?: string
  notes?: string
}

export type ChartRegistryResponse = {
  registry_version: number
  charts: ChartRegistryEntry[]
}

export type ChartBuilderInput = {
  chart_id: string
  fields: Record<string, string>
  aggregation?: string | null
  style?: Record<string, unknown>
  parent_selection_id?: string | null
  reason?: string | null
}

export async function getChartRegistry(): Promise<ChartRegistryResponse> {
  return request<ChartRegistryResponse>('/api/charts/registry')
}

export async function buildChartSelection(
  datasetId: string,
  input: ChartBuilderInput,
): Promise<ChartSelectionResult> {
  return request<ChartSelectionResult>(`/api/datasets/${datasetId}/chart-builder`, {
    method: 'POST',
    body: JSON.stringify({
      chart_id: input.chart_id,
      fields: input.fields,
      aggregation: input.aggregation ?? null,
      style: input.style ?? {},
      parent_selection_id: input.parent_selection_id ?? null,
      reason: input.reason ?? null,
    }),
  })
}
