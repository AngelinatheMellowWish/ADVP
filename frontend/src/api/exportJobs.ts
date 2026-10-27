import { request } from './projects'

export type ExportJob = {
  id: string
  kind: 'report' | 'selection'
  project_id: string | null
  target_id: string
  format: 'html' | 'pdf'
  status: string
  attempts: number
  error: string | null
  output_path: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  download_url: string | null
}

export async function createReportExport(
  runId: string,
  format: 'html' | 'pdf',
): Promise<ExportJob> {
  return request<ExportJob>(`/api/pipeline-runs/${runId}/exports`, {
    method: 'POST',
    body: JSON.stringify({ format }),
  })
}

export async function createSelectionExport(
  selectionId: string,
  format: 'html' | 'pdf',
): Promise<ExportJob> {
  return request<ExportJob>(`/api/chart-selections/${selectionId}/exports`, {
    method: 'POST',
    body: JSON.stringify({ format }),
  })
}

export async function getExportJob(jobId: string): Promise<ExportJob> {
  return request<ExportJob>(`/api/export-jobs/${jobId}`)
}

export async function retryExportJob(jobId: string): Promise<ExportJob> {
  return request<ExportJob>(`/api/export-jobs/${jobId}/retry`, { method: 'POST' })
}
