import { createRoot } from 'react-dom/client'

import { ShareShell } from './ShareShell'
import { StaticSlice } from './StaticSlice'
import type { SharePayload } from './types'

const payload: SharePayload = window.__ADVP_SHARE__ ?? {}
const render = payload.render ?? {}
const selectionId = render.selection_id ?? 'share'
const title = payload.selection?.selected?.name?.zh ?? render.chart_id ?? 'ADVP 图表'

createRoot(document.getElementById('root') as HTMLElement).render(
  <ShareShell payload={payload} renderer="vtk" selectionId={selectionId} title={title}>
    <StaticSlice slice={payload.imaging_slice} />
  </ShareShell>,
)
