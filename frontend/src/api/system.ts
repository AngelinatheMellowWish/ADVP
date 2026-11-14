import { request, requestText } from './projects'

export type ProviderStatus = {
  status: string
  name: string | null
  has_key: boolean
}

export type RecentTaskItem = {
  id: string
  kind: string
  status: string
  created_at: string
}

export type SystemStatus = {
  service: string
  provider: string | ProviderStatus
  gpu: string
  disk_free_gb: number
  database: string
  cpu_percent: number
  memory_percent: number
  network_online: boolean | null
  active_tasks?: Record<string, number>
  recent_tasks?: Record<string, RecentTaskItem[]>
}

export type AboutInfo = {
  version: string
  python: string
  platform: string
  license: string
  repository: { label: string; url: string | null }
}

export type CleanupEntry = {
  relative: string
  bytes: number
  project_id: string | null
  dataset_ids: string[]
}

export type CleanupCategory = {
  key: string
  files: number
  bytes: number
  deletable_files: number
  deletable_bytes: number
  protected_files: number
  protected_bytes: number
  affected_projects: string[]
  affected_datasets: string[]
  deletable: CleanupEntry[]
  protected: (CleanupEntry & { reason: string })[]
}

export type CleanupPreview = {
  dry_run: true
  allow_referenced_uploads: boolean
  categories: CleanupCategory[]
  totals: {
    files: number
    bytes: number
    deletable_files: number
    deletable_bytes: number
    protected_files: number
    protected_bytes: number
  }
}

export type CleanupCategoryResult = {
  key: string
  deleted_files: number
  deleted_bytes: number
  protected_files: number
  protected_bytes: number
  errors: { relative: string; reason: string }[]
}

export type CleanupResult = {
  dry_run: false
  allow_referenced_uploads: boolean
  categories: CleanupCategoryResult[]
  totals: {
    deleted_files: number
    deleted_bytes: number
    protected_files: number
    protected_bytes: number
    errors: number
  }
}

export function getSystemStatus(signal?: AbortSignal): Promise<SystemStatus> {
  return request<SystemStatus>('/api/system/status', { signal })
}

export function getAbout(): Promise<AboutInfo> {
  return request<AboutInfo>('/api/system/about')
}

export function getLicenseText(): Promise<string> {
  return requestText('/api/system/license')
}

export function getThirdPartyText(): Promise<string> {
  return requestText('/api/system/third-party')
}

export function previewCleanup(
  categories: string[],
  allowReferencedUploads = false,
): Promise<CleanupPreview> {
  return request<CleanupPreview>('/api/system/cleanup/preview', {
    method: 'POST',
    body: JSON.stringify({
      categories,
      allow_referenced_uploads: allowReferencedUploads,
    }),
  })
}

export function runCleanup(
  categories: string[],
  allowReferencedUploads = false,
): Promise<CleanupResult> {
  return request<CleanupResult>('/api/system/cleanup', {
    method: 'POST',
    body: JSON.stringify({
      categories,
      confirm: true,
      allow_referenced_uploads: allowReferencedUploads,
    }),
  })
}
