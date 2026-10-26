import { useEffect, useRef, useState } from 'react'

type PlotlyApi = {
  react: (
    root: HTMLElement,
    data: unknown[],
    layout?: Record<string, unknown>,
    config?: Record<string, unknown>,
  ) => Promise<unknown>
  purge: (root: HTMLElement) => void
  downloadImage: (root: HTMLElement, options?: Record<string, unknown>) => Promise<string>
  toImage: (root: HTMLElement, options?: Record<string, unknown>) => Promise<string>
  relayout: (root: HTMLElement, layout: Record<string, unknown>) => Promise<unknown>
}

function sanitizeSvg(svg: string): string {
  const documentNode = new DOMParser().parseFromString(svg, 'image/svg+xml')
  documentNode
    .querySelectorAll('script,foreignObject,iframe,object,embed')
    .forEach((node) => node.remove())
  for (const element of Array.from(documentNode.querySelectorAll('*'))) {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase()
      if (name.startsWith('on')) {
        element.removeAttribute(attribute.name)
      }
      if (
        (name === 'href' || name === 'xlink:href') &&
        /^\s*(javascript:|https?:|\/\/)/i.test(attribute.value)
      ) {
        element.removeAttribute(attribute.name)
      }
    }
  }
  return new XMLSerializer().serializeToString(documentNode)
}

function downloadSvg(text: string, filename: string) {
  const blob = new Blob([text], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

type FigurePayload = {
  data?: unknown[]
  layout?: Record<string, unknown>
  frames?: unknown[]
}

export function PlotlyFigure({
  figure,
  selectionId,
}: {
  figure: FigurePayload
  selectionId: string
}) {
  const container = useRef<HTMLDivElement>(null)
  const plotly = useRef<PlotlyApi | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const node = container.current
    let cancelled = false
    Promise.all([import('plotly.js-dist-min')])
      .then(([module]) => {
        if (cancelled || !node) return
        plotly.current = module.default as PlotlyApi
        return plotly.current
          .react(node, figure.data ?? [], figure.layout ?? {}, {
            responsive: true,
            displaylogo: false,
            displayModeBar: true,
            scrollZoom: true,
            modeBarButtonsToAdd: ['select2d', 'lasso2d'],
          })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Plotly 渲染失败')
        }
      })
    return () => {
      cancelled = true
      if (plotly.current && node) {
        plotly.current.purge(node)
      }
    }
  }, [figure])

  function resetView() {
    if (!container.current || !plotly.current) return
    void plotly.current.relayout(container.current, {
      'xaxis.autorange': true,
      'yaxis.autorange': true,
      'xaxis2.autorange': true,
      'yaxis2.autorange': true,
    })
  }

  async function download(format: 'png' | 'svg') {
    if (!container.current || !plotly.current) return
    if (format === 'svg') {
      const dataUrl = await plotly.current.toImage(container.current, {
        format: 'svg',
        width: 1200,
        height: 700,
        scale: 2,
      })
      const svg = await (await fetch(dataUrl)).text()
      downloadSvg(sanitizeSvg(svg), `advp-${selectionId}.svg`)
      return
    }
    await plotly.current.downloadImage(container.current, {
      format: 'png',
      filename: `advp-${selectionId}`,
      width: 1200,
      height: 700,
      scale: 2,
    })
  }

  return (
    <>
      {error ? <p className="error">{error}</p> : null}
      <div className="inline-form">
        <button className="button" onClick={resetView}>
          重置视图
        </button>
        <button className="button" onClick={() => void download('png')}>
          下载 PNG
        </button>
        <button className="button" onClick={() => void download('svg')}>
          下载 SVG
        </button>
      </div>
      <div className="chart-figure" ref={container} data-testid="chart-figure" />
    </>
  )
}
