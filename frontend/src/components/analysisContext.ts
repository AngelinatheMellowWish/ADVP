import type { DatasetDetail } from '../api/projects'
import type { EgressMode, Provider } from '../api/providers'

export type ContextColumn = {
  name: string
  physical_type: string
  semantic_type: string
  cardinality: number
  null_rate: number
  unit: string | null
  sensitive: boolean
  samples: unknown[]
  stats: Record<string, unknown>
  value_range: [unknown, unknown] | null
}

export type DatasetContext = {
  kind: string
  row_count: number
  sampled: boolean
  columns: ContextColumn[]
  quality: {
    missing_cells: number
    issue_counts: Record<string, number>
    sensitive_columns: string[]
  }
  analysis?: unknown
  preview?: Record<string, unknown>[]
}

const SAFE_STATS = new Set([
  'min',
  'max',
  'mean',
  'median',
  'std',
  'outlier_count',
  'finite_count',
  'missing_count',
])

function safeStats(stats: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(stats).filter(([key]) => SAFE_STATS.has(key)),
  )
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  const text = String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function selectDefaultProvider(providers: Provider[]): Provider | null {
  return providers.find((provider) => provider.is_default) ?? providers[0] ?? null
}

export function buildSampleCsv(
  dataset: DatasetDetail,
  maskingNote: string,
  maskedValue: string,
): string {
  const columns = dataset.schema_definition.columns
  const sensitive = new Set(
    dataset.profile.columns
      .filter((column) => column.sensitive)
      .map((column) => column.name),
  )
  const header = columns.map((column) => csvCell(column.name)).join(',')
  const rows = dataset.preview.map((row) =>
    columns
      .map((column) =>
        csvCell(sensitive.has(column.name) ? maskedValue : row[column.name]),
      )
      .join(','),
  )
  return [header, ...rows, `# ${maskingNote}`].join('\n')
}

export function buildDatasetContext(dataset: DatasetDetail): DatasetContext {
  const profile = dataset.profile as DatasetDetail['profile'] & { analysis?: unknown }
  return {
    kind: dataset.kind,
    row_count: dataset.row_count,
    sampled: dataset.sampled,
    columns: dataset.profile.columns.map((column) => ({
      name: column.name,
      physical_type: column.dtype,
      semantic_type: column.semantic_type,
      cardinality: column.cardinality,
      null_rate: column.null_rate,
      unit: column.unit,
      sensitive: column.sensitive,
      samples: column.sensitive ? [] : (column.samples ?? []).slice(0, 3),
      stats: safeStats(column.stats ?? {}),
      value_range: column.value_range,
    })),
    quality: {
      missing_cells: dataset.profile.summary?.missing_cells ?? 0,
      issue_counts: dataset.profile.summary?.issue_counts ?? {},
      sensitive_columns: dataset.profile.summary?.sensitive_columns ?? [],
    },
    analysis: profile.analysis ?? null,
  }
}

export function applyEgressPolicy(
  context: DatasetContext,
  mode: EgressMode,
  sampleRows: number,
  preview: Record<string, unknown>[],
): DatasetContext {
  const payload = JSON.parse(JSON.stringify(context)) as DatasetContext
  if (mode === 'metadata') {
    for (const column of payload.columns) column.samples = []
    delete payload.preview
    return payload
  }
  const limit = Math.max(0, Math.min(sampleRows, 100))
  for (const column of payload.columns) {
    column.samples = column.samples.slice(0, limit)
  }
  if (mode === 'full') {
    const sensitive = new Set(
      payload.columns.filter((column) => column.sensitive).map((column) => column.name),
    )
    payload.preview = preview.map((row) =>
      Object.fromEntries(
        Object.entries(row).map(([key, value]) => [
          key,
          sensitive.has(key) ? '***' : value,
        ]),
      ),
    )
  } else {
    delete payload.preview
  }
  return payload
}
