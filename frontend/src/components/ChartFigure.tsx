import { lazy, Suspense, useEffect, useState } from 'react'

import { errorMessage } from '../api/projects'
import { getChartFigure, type ChartFigureResponse } from '../api/selections'
import { CytoscapeFigure, type NetworkPayload } from './CytoscapeFigure'
import type { DeckPayload } from './DeckFigure'
import { EChartsFigure } from './EChartsFigure'
import { PlotlyFigure } from './PlotlyFigure'
import { VtkImageFigure, type ImagingPayload } from './VtkImageFigure'

const DeckFigure = lazy(() =>
  import('./DeckFigure').then((module) => ({ default: module.DeckFigure })),
)

export function ChartFigure({ selectionId }: { selectionId: string }) {
  const [payload, setPayload] = useState<ChartFigureResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setPayload(null)
    getChartFigure(selectionId)
      .then((result) => {
        if (!cancelled) setPayload(result)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectionId])

  const renderer = payload?.renderer ?? 'plotly'

  return (
    <div className="chart-figure-block">
      {loading ? <p className="muted">正在渲染图表…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {payload ? (
        <p className="muted">
          {renderer} 渲染 {payload.row_count} 行
          {payload.sampled ? '（基于采样）' : ''}
        </p>
      ) : null}
      {payload && renderer === 'plotly' ? (
        <PlotlyFigure figure={payload.figure} selectionId={payload.selection_id} />
      ) : null}
      {payload && renderer === 'echarts' ? (
        <EChartsFigure
          option={(payload.figure.option ?? {}) as Record<string, unknown>}
          selectionId={payload.selection_id}
        />
      ) : null}
      {payload && renderer === 'cytoscape' ? (
        <CytoscapeFigure
          payload={payload.figure as unknown as NetworkPayload}
          selectionId={payload.selection_id}
        />
      ) : null}
      {payload && renderer === 'deckgl' ? (
        <Suspense fallback={<p className="muted">正在加载地图渲染器…</p>}>
          <DeckFigure
            payload={payload.figure as unknown as DeckPayload}
            selectionId={payload.selection_id}
          />
        </Suspense>
      ) : null}
      {payload && renderer === 'vtk' ? (
        <VtkImageFigure
          datasetId={payload.dataset_id}
          imaging={payload.figure.imaging as unknown as ImagingPayload}
        />
      ) : null}
    </div>
  )
}
