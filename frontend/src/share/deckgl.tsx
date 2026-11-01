import { createRoot } from 'react-dom/client'

import { DeckFigure, type DeckPayload } from '../components/DeckFigure'
import { ShareShell } from './ShareShell'
import type { SharePayload } from './types'

const payload: SharePayload = window.__ADVP_SHARE__ ?? {}
const render = payload.render ?? {}
const selectionId = render.selection_id ?? 'share'
const title = payload.selection?.selected?.name?.zh ?? render.chart_id ?? 'ADVP 图表'

createRoot(document.getElementById('root') as HTMLElement).render(
  <ShareShell payload={payload} renderer="deckgl" selectionId={selectionId} title={title}>
    <DeckFigure
      payload={(render.figure ?? {}) as unknown as DeckPayload}
      selectionId={selectionId}
    />
  </ShareShell>,
)
