import { useEffect, useRef, useState } from 'react'

type EChartsInstance = {
  setOption: (option: unknown, notMerge?: boolean) => void
  resize: () => void
  dispose: () => void
  getDataURL: (options?: Record<string, unknown>) => string
}

type EChartsModule = {
  init: (node: HTMLElement, theme?: string) => EChartsInstance
}

export function EChartsFigure({
  option,
  selectionId,
}: {
  option: Record<string, unknown>
  selectionId: string
}) {
  const container = useRef<HTMLDivElement>(null)
  const chart = useRef<EChartsInstance | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const node = container.current
    let cancelled = false
    let observer: ResizeObserver | null = null
    import('echarts')
      .then((module) => {
        if (cancelled || !node) return
        const api = module as unknown as EChartsModule
        chart.current = api.init(node, 'dark')
        chart.current.setOption(option, true)
        if (typeof ResizeObserver !== 'undefined') {
          observer = new ResizeObserver(() => chart.current?.resize())
          observer.observe(node)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'ECharts 渲染失败')
        }
      })
    return () => {
      cancelled = true
      observer?.disconnect()
      chart.current?.dispose()
      chart.current = null
    }
  }, [option])

  function download() {
    if (!chart.current) return
    const url = chart.current.getDataURL({
      type: 'png',
      pixelRatio: 2,
      backgroundColor: '#0b1529',
    })
    const link = document.createElement('a')
    link.href = url
    link.download = `advp-${selectionId}.png`
    link.click()
  }

  return (
    <>
      {error ? <p className="error">{error}</p> : null}
      <div className="inline-form">
        <button className="button" onClick={download}>
          下载 PNG
        </button>
      </div>
      <div className="chart-figure" ref={container} data-testid="echarts-figure" />
    </>
  )
}
