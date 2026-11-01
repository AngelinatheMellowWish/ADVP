import { request, requestForm } from './projects'

export type ImportJobStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export type ImportJobDetail = {
  id: string
  project_id: string
  status: ImportJobStatus
  stage: string
  progress: number
  message: string | null
  payload: Record<string, unknown>
  result_dataset_id: string | null
  error: string | null
  cancel_requested: boolean
  created_at: string
  updated_at: string
}

export type UploadResponse = {
  path: string
  sha256: string
  size: number
  copied: boolean
}

export type MultiFileSource = {
  path: string
  name: string
  row_count: number
  column_count: number
  sampled: boolean
}

export type MultiFilePreview = {
  mode: 'union' | 'join'
  files: MultiFileSource[]
  columns: string[]
  left_rows: number | null
  right_rows: number | null
  result_rows: number
  match_rate: number | null
  duplicate_keys: { left: number; right: number } | null
  conflicts: string[]
  sampled: boolean
  preview: Record<string, unknown>[]
}

export type MultiFilePayload = {
  paths: string[]
  mode: 'union' | 'join'
  left_key?: string
  right_key?: string
  how?: 'inner' | 'left' | 'right' | 'full'
  name?: string | null
}

type MultiFileDataset = { id: string; row_count: number }

export async function createImportJob(
  projectId: string,
  path: string,
  name?: string,
  options?: Record<string, unknown>,
): Promise<ImportJobDetail> {
  return request<ImportJobDetail>(`/api/projects/${projectId}/import-jobs`, {
    method: 'POST',
    body: JSON.stringify({ path, name: name || null, options: options ?? {} }),
  })
}

export async function getImportJob(jobId: string): Promise<ImportJobDetail> {
  return request<ImportJobDetail>(`/api/import-jobs/${jobId}`)
}

export async function cancelImportJob(jobId: string): Promise<ImportJobDetail> {
  return request<ImportJobDetail>(`/api/import-jobs/${jobId}/cancel`, {
    method: 'POST',
  })
}

export async function retryImportJob(jobId: string): Promise<ImportJobDetail> {
  return request<ImportJobDetail>(`/api/import-jobs/${jobId}/retry`, {
    method: 'POST',
  })
}

export async function pickFile(): Promise<{ path: string | null }> {
  return request<{ path: string | null }>('/api/system/pick-file', {
    method: 'POST',
  })
}

export async function uploadFile(projectId: string, file: File): Promise<UploadResponse> {
  const body = new FormData()
  body.append('file', file)
  return requestForm<UploadResponse>(`/api/projects/${projectId}/uploads`, body)
}

export async function previewMultiFile(
  projectId: string,
  payload: MultiFilePayload,
): Promise<MultiFilePreview> {
  return request<MultiFilePreview>(`/api/projects/${projectId}/multifile/preview`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function importMultiFile(
  projectId: string,
  payload: MultiFilePayload,
): Promise<MultiFileDataset> {
  return request<MultiFileDataset>(`/api/projects/${projectId}/datasets/multifile`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
