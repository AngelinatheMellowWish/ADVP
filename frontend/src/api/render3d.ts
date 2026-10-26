import { request } from './projects'

export type RenderJob = {
  id: string
  scene_id: string
  dataset_id: string
  project_id: string
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  mode: string
  progress: number
  output: Record<string, unknown>
  error: string | null
  cancel_requested: boolean
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type RendererProbe = {
  ok: boolean
  python: string
  vtk: string | null
  mayavi: string | null
  pyside6: string | null
  gl_renderer?: string
  software_rendering?: boolean
  trame?: boolean
  imageio?: boolean
}

export async function probeRenderer(): Promise<RendererProbe> {
  return request<RendererProbe>('/api/render3d/probe')
}

export async function createRender(
  sceneId: string,
  options: {
    mode?: string
    width?: number
    height?: number
    isovalue?: number
    animation?: Record<string, unknown>
  } = {},
): Promise<RenderJob> {
  return request<RenderJob>(`/api/scenes/${sceneId}/render`, {
    method: 'POST',
    body: JSON.stringify(options),
  })
}

export async function getRenderJob(jobId: string): Promise<RenderJob> {
  return request<RenderJob>(`/api/render-jobs/${jobId}`)
}

export async function cancelRenderJob(jobId: string): Promise<RenderJob> {
  return request<RenderJob>(`/api/render-jobs/${jobId}/cancel`, { method: 'POST' })
}

export function renderDownloadUrl(jobId: string): string {
  return `/api/render-jobs/${jobId}/download`
}
