import { request } from './projects'

export type ImagingAxis = { axis: number; name: string; size: number }

export type ImagingMeta = {
  dataset_id: string
  format: string
  shape: number[]
  dims: string[]
  dtype: string | null
  units: string | null
  slice_axes: ImagingAxis[]
  volume_axis: number | null
  volume_count: number
  default_axis: number | null
  default_index: number
  window: { min: number | null; max: number | null }
}

export type ImagingSlice = {
  dataset_id: string
  axis: number
  index: number
  axis_name: string
  volume: number
  rows: number
  cols: number
  values: (number | null)[][]
  vmin: number | null
  vmax: number | null
  shape: number[]
}

export async function getImagingMeta(datasetId: string): Promise<ImagingMeta> {
  return request<ImagingMeta>(`/api/datasets/${datasetId}/imaging/meta`)
}

export async function getImagingSlice(
  datasetId: string,
  axis: number,
  index: number,
  volume = 0,
): Promise<ImagingSlice> {
  return request<ImagingSlice>(
    `/api/datasets/${datasetId}/imaging/slice?axis=${axis}&index=${index}&volume=${volume}`,
  )
}
