import { useEffect } from 'react'

import type { ImagingSlice } from '../api/imaging'

export function StaticSlice({ slice }: { slice?: ImagingSlice }) {
  useEffect(() => {
    const canvas = document.getElementById('share-slice') as HTMLCanvasElement | null
    if (!canvas || !slice) return
    const rows = slice.values.length
    const cols = slice.values[0]?.length ?? 0
    if (!rows || !cols) return
    canvas.width = cols
    canvas.height = rows
    const context = canvas.getContext('2d')
    if (!context) return
    const flat = slice.values.flat().map((value) => value ?? 0)
    const min = Math.min(...flat)
    const max = Math.max(...flat)
    const image = context.createImageData(cols, rows)
    for (let index = 0; index < flat.length; index += 1) {
      const ratio = max > min ? (flat[index] - min) / (max - min) : 0
      const value = Math.round(ratio * 255)
      image.data[index * 4] = value
      image.data[index * 4 + 1] = value
      image.data[index * 4 + 2] = value
      image.data[index * 4 + 3] = 255
    }
    context.putImageData(image, 0, 0)
  }, [slice])

  if (!slice) return <p className="muted">影像切片未包含在分享包中。</p>
  return (
    <div className="share-slice-block">
      <canvas id="share-slice" className="share-slice" />
      <p className="muted">
        {slice.axis_name} 切片 {slice.index + 1} · {slice.rows}×{slice.cols}
      </p>
    </div>
  )
}
