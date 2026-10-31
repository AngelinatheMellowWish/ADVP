export type ProjectSummary = {
  id: string
  name: string
  schema_version: number
  archived: boolean
  created_at: string
  updated_at: string
  dataset_count: number
  source_types: string[]
}

export type DatasetSummary = {
  id: string
  project_id: string
  name: string
  version: number
  kind: string
  format: string
  source_path: string
  source_sha256: string
  source_size: number
  row_count: number
  row_count_estimated: boolean
  column_count: number
  sampled: boolean
  quality_score: number
  created_at: string
  updated_at: string
}

export type ColumnDefinition = {
  name: string
  physical_type: string
  semantic_type: string
  nullable: boolean
  cardinality: number
  value_range: [unknown, unknown] | null
  unit: string | null
  source_column: string
}

export type VariableInfo = {
  name: string
  path: string
  shape: number[]
  dtype: string
  dims: string[]
  units: string | null
}

export type ArrayProfile = {
  shape: number[]
  dims: string[]
  dtype: string
  units: string | null
  stats: Record<string, number | null>
}

export type SchemaDefinition = {
  version: number
  kind?: string
  variable?: string
  shape?: number[]
  dims?: string[]
  dtype?: string
  units?: string | null
  columns: ColumnDefinition[]
}

export type ImportOptionsInput = {
  variable?: string
  shape?: number[]
  dtype?: string
  byte_order?: string
  raw_offset?: number
}

export type ProfileIssue = {
  code: string
  severity: 'blocking' | 'warning' | 'info'
  message: string
  suggestion?: string
  column?: string | null
  affected_rows?: number | null
}

export type ColumnProfile = {
  name: string
  dtype: string
  semantic_type: string
  nullable: boolean
  null_count: number
  null_rate: number
  n_unique: number
  cardinality: number
  value_range: [unknown, unknown] | null
  unit: string | null
  source_column: string
  sensitive: boolean
  sensitive_kind: string | null
  stats: Record<string, unknown>
  top_values: { value: unknown; count: number | null }[]
  samples: unknown[]
}

export type Profile = {
  quality_score: number
  sampled: boolean
  sample_rows: number
  total_rows: number
  row_count_estimated: boolean
  duplicate_rows: number
  columns: ColumnProfile[]
  issues: ProfileIssue[]
  summary: {
    missing_cells: number
    sensitive_columns: string[]
    issue_counts: Record<string, number>
  }
  import_issues?: ProfileIssue[]
  kind?: string
  array?: ArrayProfile | null
}

export type DatasetDetail = DatasetSummary & {
  options: Record<string, unknown>
  schema_definition: SchemaDefinition
  profile: Profile
  preview: Record<string, unknown>[]
  ignored_issues: string[]
}

export type ProjectDetail = ProjectSummary & {
  settings: Record<string, unknown>
  datasets: DatasetSummary[]
  migration: {
    from: number
    to: number
    applied: string[]
    backup: string
  } | null
}

export type InspectResponse = {
  kind: string
  path: string
  format: string
  size_bytes: number
  mtime: number
  row_count: number
  column_count: number
  row_count_estimated: boolean
  sampled: boolean
  options: Record<string, unknown>
  detected: Record<string, unknown>
  schema_definition: SchemaDefinition
  profile: Profile
  preview: Record<string, unknown>[]
  issues: ProfileIssue[]
  variables: VariableInfo[]
}

export type PreviewResponse = {
  rows: Record<string, unknown>[]
  columns: ColumnDefinition[]
  limit: number
  offset: number
  total_rows: number
  sampled: boolean
}

export type ChartIntent =
  | 'trend'
  | 'distribution'
  | 'comparison'
  | 'correlation'
  | 'composition'
  | 'timeline'

export type ChartCandidate = {
  id: string
  name: { zh: string; en: string }
  family: string
  backend: string
  rule_rank: number
  suggested_fields: Record<string, string>
  array_mapping: {
    value: string
    slice_axis: string | null
    slice_index: number | null
    display_shape: number[]
  } | null
  why: string
  supports: string[]
  accessibility_notes: string
  notes: string
}

export type ExcludedChart = {
  id: string
  reason_code: string
  message: string
}

export type ChartCandidatesResponse = {
  kind: string
  dataset_id: string | null
  intent: ChartIntent | null
  registry_version: number
  row_count: number | null
  candidates: ChartCandidate[]
  excluded: ExcludedChart[]
}

export type SqlConnectionResult = {
  ok: boolean
  dialect: string
  database: string
  label: string
}

export type SqlTableInfo = {
  name: string
  schema_name: string | null
  type: string
}

export type SqlColumnInfo = {
  name: string
  type: string
  nullable: boolean
  default: string | null
}

export type SqlPreviewResponse = {
  rows: Record<string, unknown>[]
  columns: ColumnDefinition[]
  limit: number
  offset: number
  truncated: boolean
  dialect: string
}

export type DocumentTableInfo = {
  index: number
  source: string
  page: number | null
  table_index: number
  row_count: number
  column_count: number
  confidence: number
  headers: string[]
  preview: string[][]
}

export type TextFact = {
  fact_id?: string | null
  subject_path: string
  metric: string
  value_text?: string | null
  value_number?: number | null
  value_low?: number | null
  value_high?: number | null
  unit?: string | null
  qualifier?: string | null
  relation?: string
  note?: string | null
  source?: Record<string, unknown>
  confidence?: number
  include?: boolean
  edited?: boolean
}

export type TextStatsWarning = {
  code: string
  severity?: string
  message: string
}

export type TextStatsLong = {
  facts: TextFact[]
  rows: Record<string, unknown>[]
  warnings: TextStatsWarning[]
}

export type TextStatsWide = {
  headers: string[]
  rows: Record<string, unknown>[]
  warnings: TextStatsWarning[]
}

export type TextStatsExtraction = {
  char_count: number
  paragraph_count: number
  has_numbers: boolean
  truncated: boolean
  extractor: { version: string; method: string }
  long: TextStatsLong
  wide: TextStatsWide
}

export type DocumentTablesResponse = {
  path: string
  format: string
  source_sha256: string
  tables: DocumentTableInfo[]
  text?: TextStatsExtraction | null
}

export type TextStatsImportResult = DatasetDetail

export type WebTableInfo = {
  index: number
  row_count: number
  column_count: number
  confidence: number
  headers: string[]
  preview: string[][]
}

export type WebTablesResponse = {
  url: string
  format: string
  tables: WebTableInfo[]
}

export type StreamPreviewResponse = {
  records: Record<string, unknown>[]
  count: number
  source: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly hint?: string

  constructor(message: string, status: number, code: string, hint?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.hint = hint
  }
}

type ErrorDetail = { code?: string; message?: string; hint?: string }

let sessionPromise: Promise<void> | null = null

async function ensureSession(): Promise<void> {
  if (sessionPromise) return sessionPromise
  const token = new URLSearchParams(window.location.search).get('token')
  if (!token) return
  sessionPromise = fetch(`/api/session?token=${encodeURIComponent(token)}`, {
    credentials: 'same-origin',
  })
    .then((response) => {
      if (!response.ok) throw new Error('本地会话初始化失败')
      const url = new URL(window.location.href)
      url.searchParams.delete('token')
      window.history.replaceState({}, '', url.pathname + url.search + url.hash)
    })
    .catch((error: unknown) => {
      sessionPromise = null
      throw error
    })
  return sessionPromise
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  await ensureSession()
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...init,
  })
  return parseResponse<T>(response)
}

export async function requestForm<T>(path: string, body: FormData): Promise<T> {
  await ensureSession()
  const response = await fetch(path, {
    method: 'POST',
    body,
    credentials: 'same-origin',
  })
  return parseResponse<T>(response)
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: ErrorDetail | null = null
    try {
      const payload = (await response.json()) as { detail?: ErrorDetail }
      detail = payload.detail ?? null
    } catch {
      detail = null
    }
    throw new ApiError(
      detail?.message ?? `请求失败 (${response.status})`,
      response.status,
      detail?.code ?? 'api_error',
      detail?.hint,
    )
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.hint ? `${error.message}：${error.hint}` : error.message
  }
  return error instanceof Error ? error.message : '未知错误'
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(2)} ${units[index]}`
}

export async function listProjects(includeArchived = false): Promise<ProjectSummary[]> {
  return request<ProjectSummary[]>(
    `/api/projects?include_archived=${includeArchived ? 'true' : 'false'}`,
  )
}

export async function createProject(name: string): Promise<ProjectDetail> {
  return request<ProjectDetail>('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/api/projects/${projectId}`)
}

export async function updateProject(
  projectId: string,
  patch: { name?: string; archived?: boolean },
): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/api/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export async function deleteProject(projectId: string): Promise<void> {
  await request<void>(`/api/projects/${projectId}`, { method: 'DELETE' })
}

export async function revealProject(projectId: string): Promise<{ path: string }> {
  return request<{ path: string }>(`/api/projects/${projectId}/reveal`, {
    method: 'POST',
  })
}

export async function inspectDataset(
  projectId: string,
  path: string,
  options?: ImportOptionsInput,
): Promise<InspectResponse> {
  return request<InspectResponse>(`/api/projects/${projectId}/datasets/inspect`, {
    method: 'POST',
    body: JSON.stringify({ path, options: options ?? {} }),
  })
}

export async function importDataset(
  projectId: string,
  path: string,
  name?: string,
  options?: ImportOptionsInput,
): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/projects/${projectId}/datasets`, {
    method: 'POST',
    body: JSON.stringify({ path, name: name || null, options: options ?? {} }),
  })
}

export async function getDataset(datasetId: string): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/datasets/${datasetId}`)
}

export async function fetchChartCandidates(
  datasetId: string,
  intent?: ChartIntent,
): Promise<ChartCandidatesResponse> {
  return request<ChartCandidatesResponse>(`/api/datasets/${datasetId}/chart-candidates`, {
    method: 'POST',
    body: JSON.stringify({ intent: intent ?? null }),
  })
}

export async function getPreview(
  datasetId: string,
  limit = 20,
  offset = 0,
): Promise<PreviewResponse> {
  return request<PreviewResponse>(
    `/api/datasets/${datasetId}/preview?limit=${limit}&offset=${offset}`,
  )
}

export async function reprofileDataset(datasetId: string): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/datasets/${datasetId}/reprofile`, {
    method: 'POST',
  })
}

export async function relocateDataset(
  datasetId: string,
  path: string,
  force = false,
): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/datasets/${datasetId}/relocate`, {
    method: 'POST',
    body: JSON.stringify({ path, force }),
  })
}

export async function getManifest(projectId: string): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>(`/api/projects/${projectId}/manifest`)
}

export async function testSqlConnection(url: string): Promise<SqlConnectionResult> {
  return request<SqlConnectionResult>('/api/sql/test', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

export async function listSqlTables(
  url: string,
): Promise<{ dialect: string; tables: SqlTableInfo[] }> {
  return request<{ dialect: string; tables: SqlTableInfo[] }>('/api/sql/tables', {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

export async function listSqlColumns(
  url: string,
  table: string,
): Promise<{ dialect: string; table: string; columns: SqlColumnInfo[] }> {
  return request<{ dialect: string; table: string; columns: SqlColumnInfo[] }>(
    '/api/sql/columns',
    {
      method: 'POST',
      body: JSON.stringify({ url, table }),
    },
  )
}

export async function previewSql(
  url: string,
  query: string,
  limit = 100,
  offset = 0,
): Promise<SqlPreviewResponse> {
  return request<SqlPreviewResponse>('/api/sql/preview', {
    method: 'POST',
    body: JSON.stringify({ url, query, limit, offset }),
  })
}

export async function importSqlDataset(
  projectId: string,
  url: string,
  query: string,
  name?: string,
  maxRows = 100_000,
): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/projects/${projectId}/datasets/sql`, {
    method: 'POST',
    body: JSON.stringify({ url, query, name: name || null, max_rows: maxRows }),
  })
}

export async function importRemote(
  projectId: string,
  url: string,
  name?: string,
  token?: string,
): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/projects/${projectId}/datasets/remote`, {
    method: 'POST',
    body: JSON.stringify({
      url,
      name: name || null,
      auth: token ? { type: 'bearer', token } : null,
    }),
  })
}

export async function inspectDocument(
  projectId: string,
  path: string,
): Promise<DocumentTablesResponse> {
  return request<DocumentTablesResponse>(
    `/api/projects/${projectId}/documents/inspect`,
    { method: 'POST', body: JSON.stringify({ path }) },
  )
}

export async function importDocument(
  projectId: string,
  path: string,
  tableIndex: number,
  name?: string,
  hasHeader = true,
): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/projects/${projectId}/datasets/document`, {
    method: 'POST',
    body: JSON.stringify({
      path,
      table_index: tableIndex,
      name: name || null,
      has_header: hasHeader,
    }),
  })
}

export async function importTextStats(
  projectId: string,
  path: string,
  sourceSha256: string,
  shape: 'long' | 'wide',
  facts: TextFact[],
  name?: string,
  ai?: Record<string, unknown> | null,
): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/projects/${projectId}/datasets/text`, {
    method: 'POST',
    body: JSON.stringify({
      path,
      source_sha256: sourceSha256,
      shape,
      name: name || null,
      facts,
      ai: ai ?? null,
    }),
  })
}

export async function enhanceTextStats(
  projectId: string,
  path: string,
  sourceSha256: string,
  facts: TextFact[],
  providerId?: string,
): Promise<{
  source_sha256: string
  facts: TextFact[]
  warnings: TextStatsWarning[]
  ai: Record<string, unknown>
}> {
  return request(`/api/projects/${projectId}/documents/text/ai`, {
    method: 'POST',
    body: JSON.stringify({
      path,
      source_sha256: sourceSha256,
      facts,
      allow_ai: true,
      provider_id: providerId ?? null,
    }),
  })
}

export async function inspectWeb(
  projectId: string,
  url: string,
): Promise<WebTablesResponse> {
  return request<WebTablesResponse>(`/api/projects/${projectId}/web/inspect`, {
    method: 'POST',
    body: JSON.stringify({ url }),
  })
}

export async function importWeb(
  projectId: string,
  url: string,
  tableIndex: number,
  name?: string,
): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/projects/${projectId}/datasets/web`, {
    method: 'POST',
    body: JSON.stringify({ url, table_index: tableIndex, name: name || null }),
  })
}

export async function previewWebSocket(
  url: string,
  maxMessages = 50,
  timeout = 10,
): Promise<StreamPreviewResponse> {
  return request<StreamPreviewResponse>('/api/streams/websocket/preview', {
    method: 'POST',
    body: JSON.stringify({ url, max_messages: maxMessages, timeout }),
  })
}

export async function importWebSocket(
  projectId: string,
  url: string,
  name?: string,
  maxMessages = 50,
  timeout = 10,
): Promise<DatasetDetail> {
  return request<DatasetDetail>(
    `/api/projects/${projectId}/datasets/websocket`,
    {
      method: 'POST',
      body: JSON.stringify({
        url,
        name: name || null,
        max_messages: maxMessages,
        timeout,
      }),
    },
  )
}

export async function previewKafka(
  bootstrap: string,
  topic: string,
  maxMessages = 50,
  timeout = 10,
): Promise<StreamPreviewResponse> {
  return request<StreamPreviewResponse>('/api/streams/kafka/preview', {
    method: 'POST',
    body: JSON.stringify({
      bootstrap,
      topic,
      max_messages: maxMessages,
      timeout,
    }),
  })
}

export async function importKafka(
  projectId: string,
  bootstrap: string,
  topic: string,
  name?: string,
  maxMessages = 50,
  timeout = 10,
): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/projects/${projectId}/datasets/kafka`, {
    method: 'POST',
    body: JSON.stringify({
      bootstrap,
      topic,
      name: name || null,
      max_messages: maxMessages,
      timeout,
    }),
  })
}
