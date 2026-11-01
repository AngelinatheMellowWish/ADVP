import { request } from './projects'

export type AnalysisCorrelation = {
  left: string
  right: string
  r: number
  strength: string
}

export type DatasetAnalysis = {
  version: number
  computed_at: string
  sample_size: number
  sampled: boolean
  numeric_columns: {
    name: string
    count: number
    mean: number
    median: number
    std: number
    min: number
    max: number
    skewness: number
  }[]
  correlations: AnalysisCorrelation[]
  temporal: {
    name: string
    count: number
    start: string
    end: string
    span_seconds: number
    median_gap_seconds: number | null
    max_gap_seconds: number | null
  }[]
  geo: {
    columns: string[]
    latitude?: { name: string; min: number; max: number }
    longitude?: { name: string; min: number; max: number }
    center?: [number | null, number]
  } | null
  categorical: {
    name: string
    cardinality: number
    sensitive: boolean
    top: { value: unknown; count: number | null }[]
  }[]
  notes: string[]
  summary: string
  array?: {
    shape: number[]
    dims: string[]
    dtype: string
    units: string | null
    stats: Record<string, unknown>
  }
}

export type AnalysisResponse = {
  dataset_id: string
  analysis: DatasetAnalysis
}

export async function getDatasetAnalysis(datasetId: string): Promise<AnalysisResponse> {
  return request<AnalysisResponse>(`/api/datasets/${datasetId}/analysis`)
}

export async function computeDatasetAnalysis(datasetId: string): Promise<AnalysisResponse> {
  return request<AnalysisResponse>(`/api/datasets/${datasetId}/analysis`, {
    method: 'POST',
  })
}
