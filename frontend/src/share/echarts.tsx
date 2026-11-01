import { createRoot } from 'react-dom/client'

import { EChartsFigure } from '../components/EChartsFigure'
import { ShareShell } from './ShareShell'
import type { SharePayload } from './types'

const payload: SharePayload = window.__ADVP_SHARE__ ?? {}
const render = payload.render ?? {}
const selectionId = render.selection_id ?? 'share'
const title = payload.selection?.selected?.name?.zh ?? render.chart_id ?? 'ADVP 图表'
const figure = render.figure ?? {}

createRoot(document.getElementById('root') as HTMLElement).render(
  <ShareShell payload={payload} renderer="echarts" selectionId={selectionId} title={title}>
    <EChartsFigure
      option={(figure.option ?? {}) as Record<string, unknown>}
      selectionId={selectionId}
    />
  </ShareShell>,
)
