import type { ImagingSlice } from '../api/imaging'

export type SharePayload = {
  selection?: {
    selected?: {
      chart_id?: string
      name?: { zh?: string; en?: string }
      reason?: string
      fields?: Record<string, string>
      style?: Record<string, unknown> | null
      score?: number
    }
  }
  render?: {
    selection_id?: string
    dataset_id?: string
    chart_id?: string
    renderer?: string
    figure?: Record<string, unknown>
    row_count?: number
    sampled?: boolean
  }
  dataset?: { name?: string; format?: string; row_count?: number }
  imaging_slice?: ImagingSlice
}

declare global {
  interface Window {
    __ADVP_SHARE__?: SharePayload
    __ADVP_READY__?: boolean
  }
}
