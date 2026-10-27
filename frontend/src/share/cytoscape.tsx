import { createRoot } from 'react-dom/client'

import { CytoscapeFigure, type NetworkPayload } from '../components/CytoscapeFigure'
import { ShareShell } from './ShareShell'
import type { SharePayload } from './types'

const payload: SharePayload = window.__ADVP_SHARE__ ?? {}
const render = payload.render ?? {}
const selectionId = render.selection_id ?? 'share'
const title = payload.selection?.selected?.name?.zh ?? render.chart_id ?? 'ADVP 图表'

createRoot(document.getElementById('root') as HTMLElement).render(
  <ShareShell payload={payload} renderer="cytoscape" selectionId={selectionId} title={title}>
    <CytoscapeFigure
      payload={(render.figure ?? {}) as unknown as NetworkPayload}
      selectionId={selectionId}
    />
  </ShareShell>,
)
