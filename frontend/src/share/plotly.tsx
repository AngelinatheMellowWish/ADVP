import { createRoot } from 'react-dom/client'

import { PlotlyFigure } from '../components/PlotlyFigure'
import { ShareShell } from './ShareShell'
import type { SharePayload } from './types'

const payload: SharePayload = window.__ADVP_SHARE__ ?? {}
const render = payload.render ?? {}
const selectionId = render.selection_id ?? 'share'
const title = payload.selection?.selected?.name?.zh ?? render.chart_id ?? 'ADVP 图表'

createRoot(document.getElementById('root') as HTMLElement).render(
  <ShareShell payload={payload} renderer="plotly" selectionId={selectionId} title={title}>
    <PlotlyFigure
      figure={(render.figure ?? {}) as { data?: unknown[]; layout?: Record<string, unknown> }}
      selectionId={selectionId}
    />
  </ShareShell>,
)
