import { useEffect, useRef, useState } from 'react'

type CyData = { id?: string; label?: string; weight?: number; source?: string; target?: string }
type CyElement = { data: CyData }
type CyNode = { data: (key?: string) => unknown }
type CyCollection = {
  filter: (predicate: (node: CyNode) => boolean) => CyCollection
  style: (key: string, value: string) => void
}
type CyInstance = {
  destroy: () => void
  fit: (elements?: unknown, padding?: number) => void
  layout: (options: Record<string, unknown>) => { run: () => void }
  nodes: () => CyCollection
  png: (options: Record<string, unknown>) => string
}
type CytoscapeModule = (options: Record<string, unknown>) => CyInstance

export type NetworkPayload = {
  elements?: { nodes?: CyElement[]; edges?: CyElement[] }
  layouts?: string[]
  style?: { title?: string | null; color?: string | null }
  meta?: { node_count?: number; edge_count?: number; truncated_nodes?: boolean }
  title?: string
}

const LAYOUT_LABELS: Record<string, string> = {
  cose: '力导向',
  circle: '环形',
  grid: '网格',
  breadthfirst: '层次',
}

export function CytoscapeFigure({
  payload,
  selectionId,
}: {
  payload: NetworkPayload
  selectionId: string
}) {
  const container = useRef<HTMLDivElement>(null)
  const cy = useRef<CyInstance | null>(null)
  const [layout, setLayout] = useState('cose')
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const node = container.current
    let cancelled = false
    import('cytoscape')
      .then((module) => {
        if (cancelled || !node) return
        const api = module.default as unknown as CytoscapeModule
        const elements = [
          ...(payload.elements?.nodes ?? []),
          ...(payload.elements?.edges ?? []),
        ]
        cy.current = api({
          container: node,
          elements,
          style: [
            {
              selector: 'node',
              style: {
                'background-color': '#2f80ed',
                label: 'data(label)',
                color: '#dbeafe',
                'font-size': 10,
                'text-valign': 'center',
                'text-outline-color': '#0b1529',
                'text-outline-width': 1,
                width: 18,
                height: 18,
              },
            },
            {
              selector: 'edge',
              style: {
                width: 'mapData(weight, 0, 10, 1, 6)',
                'line-color': '#4b6a94',
                'target-arrow-color': '#4b6a94',
                'target-arrow-shape': 'triangle',
                'curve-style': 'bezier',
                opacity: 0.72,
              },
            },
          ],
          layout: { name: 'cose', animate: false, padding: 24 },
          wheelSensitivity: 0.2,
        })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Cytoscape 渲染失败')
        }
      })
    return () => {
      cancelled = true
      cy.current?.destroy()
      cy.current = null
    }
  }, [payload])

  useEffect(() => {
    if (!cy.current) return
    cy.current.layout({ name: layout, animate: false, padding: 24 }).run()
  }, [layout])

  useEffect(() => {
    if (!cy.current) return
    const text = query.trim().toLowerCase()
    const nodes = cy.current.nodes()
    nodes.style('display', 'none')
    const matched = text
      ? nodes.filter((node) => String(node.data('id') ?? '').toLowerCase().includes(text))
      : nodes
    matched.style('display', 'element')
    cy.current.fit(undefined, 30)
  }, [query])

  function reset() {
    if (!cy.current) return
    cy.current.fit(undefined, 30)
  }

  function download() {
    if (!cy.current) return
    const url = cy.current.png({ scale: 2, full: true, bg: '#0b1529' })
    const link = document.createElement('a')
    link.href = url
    link.download = `advp-${selectionId}.png`
    link.click()
  }

  const meta = payload.meta ?? {}
  return (
    <>
      {error ? <p className="error">{error}</p> : null}
      <div className="chart-controls">
        <label>
          布局
          <select value={layout} onChange={(event) => setLayout(event.target.value)}>
            {(payload.layouts ?? ['cose']).map((name) => (
              <option key={name} value={name}>
                {LAYOUT_LABELS[name] ?? name}
              </option>
            ))}
          </select>
        </label>
        <label>
          节点过滤
          <input
            aria-label="节点过滤"
            placeholder="输入节点 ID"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button className="button" onClick={reset}>
          复位
        </button>
        <button className="button" onClick={download}>
          下载 PNG
        </button>
      </div>
      <p className="muted">
        {meta.node_count ?? 0} 个节点 · {meta.edge_count ?? 0} 条边
        {meta.truncated_nodes ? ' · 已截断到显示上限' : ''}
      </p>
      <div className="chart-figure chart-network" ref={container} data-testid="cytoscape-figure" />
    </>
  )
}
