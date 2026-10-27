import { request } from './projects'

export type SceneCamera = {
  position: number[]
  focalPoint: number[]
  viewUp: number[]
}

export type SceneDocument = {
  version: string
  data: {
    datasetId: string
    fields: string[]
    coordinates: { x?: string | null; y?: string | null; z?: string | null; units?: string | null }
  }
  geometry: {
    type: string
    dimensions?: number[] | null
    spacing?: number[] | null
    origin?: number[] | null
    axis?: number | null
    index?: number | null
    level?: number | null
    variable?: string | null
  }
  camera: SceneCamera
  lighting: { ambient: number; diffuse: number }
  colormap: { name: string; range: number[]; nanColor: string }
  transferFunction: { points: number[][] }
  clipping: { enabled: boolean; planes: Record<string, unknown>[] }
  annotations: { text: string; position: number[]; color?: string | null }[]
  animation: {
    frames: number
    fps: number
    resolution: number[]
    cameraPath: number[][]
    startFrame?: number
  }
  backend: 'auto' | 'webgl' | 'mayavi' | 'trame'
  sampling: { maxElements: number; mode: 'stride' | 'none' }
  scientific: {
    coordinateReference?: string | null
    units?: string | null
    dataRange?: number[] | null
  }
}

export type SceneRecord = {
  id: string
  dataset_id: string
  project_id: string
  version: string
  scene: SceneDocument
  scene_hash: string
  created_at: string
  updated_at: string
}

export type GeometryPayload = {
  mode: string
  dataset_id: string
  fields?: Record<string, string | null>
  points?: { position: number[]; value?: number }[]
  values?: (number | null)[][] | (number | null)[] | null
  rows?: number
  cols?: number
  axis?: number
  index?: number
  axis_name?: string
  shape?: number[]
  source_shape?: number[]
  display_shape?: number[]
  dims?: string[]
  dtype?: string | null
  units?: string | null
  range?: [number | null, number | null] | null
  sampled?: boolean
  lod?: number
  variable?: string
  volume?: number
  volume_count?: number
  spacing?: number[]
  origin?: number[]
}

export async function createScene(
  datasetId: string,
  scene: Record<string, unknown>,
): Promise<SceneRecord> {
  return request<SceneRecord>(`/api/datasets/${datasetId}/scenes`, {
    method: 'POST',
    body: JSON.stringify(scene),
  })
}

export async function getScene(sceneId: string): Promise<SceneRecord> {
  return request<SceneRecord>(`/api/scenes/${sceneId}`)
}

export async function patchScene(
  sceneId: string,
  scene: Record<string, unknown>,
): Promise<SceneRecord> {
  return request<SceneRecord>(`/api/scenes/${sceneId}`, {
    method: 'PATCH',
    body: JSON.stringify(scene),
  })
}

export async function validateScene(sceneId: string): Promise<{
  valid: boolean
  scene: SceneDocument
  manifest: Record<string, unknown>
}> {
  return request(`/api/scenes/${sceneId}/validate`, { method: 'POST' })
}

export async function getGeometry(
  datasetId: string,
  params: Record<string, string | number | undefined>,
): Promise<GeometryPayload> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  return request<GeometryPayload>(`/api/datasets/${datasetId}/3d/geometry?${query.toString()}`)
}
