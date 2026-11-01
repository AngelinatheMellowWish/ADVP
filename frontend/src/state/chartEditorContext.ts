import { createContext, useContext } from 'react'

export type ChartStyle = {
  title?: string
  color?: string
  legend_position?: string
  log_x?: boolean
  log_y?: boolean
  dual_y?: boolean
  colorblind_palette?: boolean
  barmode?: string
}

export type ChartDraft = {
  chartId: string
  fields: Record<string, string>
  aggregation: string
  style: ChartStyle
}

export type ChartTab = {
  id: string
  draft: ChartDraft
  selectionId: string | null
  history: ChartDraft[]
  future: ChartDraft[]
}

export type ChartEditorContextValue = {
  tabs: ChartTab[]
  activeId: string
  activeTab: ChartTab
  canUndo: boolean
  canRedo: boolean
  setChart: (chartId: string, fields?: Record<string, string>) => void
  updateField: (role: string, value: string) => void
  setAggregation: (value: string) => void
  updateStyle: (patch: Partial<ChartStyle>) => void
  undo: () => void
  redo: () => void
  reset: () => void
  setSelectionId: (value: string | null) => void
  addTab: () => void
  closeTab: (id: string) => void
  selectTab: (id: string) => void
}

export const emptyDraft = (chartId = 'bar'): ChartDraft => ({
  chartId,
  fields: {},
  aggregation: '',
  style: {},
})

export const cloneDraft = (draft: ChartDraft): ChartDraft => ({
  chartId: draft.chartId,
  fields: { ...draft.fields },
  aggregation: draft.aggregation,
  style: { ...draft.style },
})

export const ChartEditorContext = createContext<ChartEditorContextValue | null>(null)

export function useChartEditor(): ChartEditorContextValue {
  const value = useContext(ChartEditorContext)
  if (!value) {
    throw new Error('useChartEditor must be used within ChartEditorProvider')
  }
  return value
}
