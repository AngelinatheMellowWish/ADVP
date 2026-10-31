import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'

import {
  ChartEditorContext,
  cloneDraft,
  emptyDraft,
  type ChartDraft,
  type ChartStyle,
  type ChartTab,
} from './chartEditorContext'

function newTab(id: string, chartId = 'bar'): ChartTab {
  return {
    id,
    draft: emptyDraft(chartId),
    selectionId: null,
    history: [],
    future: [],
  }
}

export function ChartEditorProvider({ children }: { children: ReactNode }) {
  const counter = useRef(1)
  const [tabs, setTabs] = useState<ChartTab[]>(() => [newTab('chart-1')])
  const [activeId, setActiveId] = useState('chart-1')

  const commit = useCallback((mutate: (draft: ChartDraft) => ChartDraft) => {
    setTabs((current) =>
      current.map((tab) => {
        if (tab.id !== activeId) return tab
        const next = mutate(cloneDraft(tab.draft))
        return {
          ...tab,
          draft: next,
          history: [...tab.history, cloneDraft(tab.draft)].slice(-50),
          future: [],
        }
      }),
    )
  }, [activeId])

  const setChart = useCallback(
    (chartId: string, fields?: Record<string, string>) => {
      commit((draft) => ({
        ...draft,
        chartId,
        fields: fields ? { ...fields } : {},
      }))
    },
    [commit],
  )

  const updateField = useCallback(
    (role: string, value: string) => {
      commit((draft) => {
        const fields = { ...draft.fields }
        if (value) fields[role] = value
        else delete fields[role]
        return { ...draft, fields }
      })
    },
    [commit],
  )

  const setAggregation = useCallback(
    (value: string) => {
      commit((draft) => ({ ...draft, aggregation: value }))
    },
    [commit],
  )

  const updateStyle = useCallback(
    (patch: Partial<ChartStyle>) => {
      commit((draft) => ({ ...draft, style: { ...draft.style, ...patch } }))
    },
    [commit],
  )

  const undo = useCallback(() => {
    setTabs((current) =>
      current.map((tab) => {
        if (tab.id !== activeId || tab.history.length === 0) return tab
        const history = [...tab.history]
        const previous = history.pop()
        if (!previous) return tab
        return {
          ...tab,
          draft: previous,
          history,
          future: [cloneDraft(tab.draft), ...tab.future].slice(0, 50),
        }
      }),
    )
  }, [activeId])

  const redo = useCallback(() => {
    setTabs((current) =>
      current.map((tab) => {
        if (tab.id !== activeId || tab.future.length === 0) return tab
        const [next, ...future] = tab.future
        return {
          ...tab,
          draft: next,
          history: [...tab.history, cloneDraft(tab.draft)].slice(-50),
          future,
        }
      }),
    )
  }, [activeId])

  const reset = useCallback(() => {
    commit((draft) => ({ ...emptyDraft(draft.chartId) }))
  }, [commit])

  const setSelectionId = useCallback(
    (value: string | null) => {
      setTabs((current) =>
        current.map((tab) =>
          tab.id === activeId ? { ...tab, selectionId: value } : tab,
        ),
      )
    },
    [activeId],
  )

  const addTab = useCallback(() => {
    counter.current += 1
    const id = `chart-${counter.current}`
    setTabs((current) => [...current, newTab(id)])
    setActiveId(id)
  }, [])

  const closeTab = useCallback(
    (id: string) => {
      if (tabs.length <= 1) return
      const index = tabs.findIndex((tab) => tab.id === id)
      const remaining = tabs.filter((tab) => tab.id !== id)
      setTabs(remaining)
      if (!remaining.some((tab) => tab.id === activeId)) {
        const nextIndex = Math.max(0, Math.min(index, remaining.length - 1))
        setActiveId(remaining[nextIndex].id)
      }
    },
    [tabs, activeId],
  )

  const selectTab = useCallback((id: string) => {
    setActiveId(id)
  }, [])

  const activeTab = tabs.find((tab) => tab.id === activeId) ?? tabs[0]

  const value = useMemo(
    () => ({
      tabs,
      activeId,
      activeTab,
      canUndo: activeTab.history.length > 0,
      canRedo: activeTab.future.length > 0,
      setChart,
      updateField,
      setAggregation,
      updateStyle,
      undo,
      redo,
      reset,
      setSelectionId,
      addTab,
      closeTab,
      selectTab,
    }),
    [
      tabs,
      activeId,
      activeTab,
      setChart,
      updateField,
      setAggregation,
      updateStyle,
      undo,
      redo,
      reset,
      setSelectionId,
      addTab,
      closeTab,
      selectTab,
    ],
  )

  return <ChartEditorContext.Provider value={value}>{children}</ChartEditorContext.Provider>
}
