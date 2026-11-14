import { useTranslation } from 'react-i18next'

import type { TraceNode } from '../api/trace'

type ModelCost = {
  model: string
  cost: number
  requests: number
}

export function TraceCostTimeline({
  nodes,
  totalCost,
  currency,
}: {
  nodes: TraceNode[]
  totalCost: number
  currency: string
}) {
  const { t } = useTranslation()
  const byModel = new Map<string, ModelCost>()
  for (const node of nodes) {
    if (!node.model) continue
    const current = byModel.get(node.model) ?? { model: node.model, cost: 0, requests: 0 }
    current.cost += Number(node.estimated_cost) || 0
    current.requests += 1
    byModel.set(node.model, current)
  }
  const models = [...byModel.values()].sort((left, right) => right.cost - left.cost)

  return (
    <section className="trace-cost-timeline" data-testid="trace-cost-timeline">
      <h4>{t('tracePage.costTimeline.title')}</h4>
      <p className="muted" data-testid="trace-cost-total">
        {t('tracePage.costTimeline.total')}: {totalCost.toFixed(6)} {currency}
      </p>
      <div className="table-wrap">
        <table className="preview-table">
          <thead>
            <tr>
              <th>{t('tracePage.costTimeline.step')}</th>
              <th>{t('tracePage.costTimeline.duration')}</th>
              <th>{t('tracePage.costTimeline.model')}</th>
              <th>{t('tracePage.costTimeline.cost')}</th>
            </tr>
          </thead>
          <tbody>
            {nodes.map((node) => (
              <tr key={node.id} data-testid={`trace-cost-step-${node.key}`}>
                <td>{node.name}</td>
                <td>{node.duration_ms} ms</td>
                <td>{node.model ?? '—'}</td>
                <td>
                  {Number(node.estimated_cost).toFixed(6)} {node.currency}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h5>{t('tracePage.costTimeline.byModel')}</h5>
      {models.length > 0 ? (
        <div className="table-wrap">
          <table className="preview-table">
            <thead>
              <tr>
                <th>{t('tracePage.costTimeline.model')}</th>
                <th>{t('tracePage.costTimeline.cost')}</th>
              </tr>
            </thead>
            <tbody>
              {models.map((item) => (
                <tr key={item.model} data-testid={`trace-cost-model-${item.model}`}>
                  <td>{item.model}</td>
                  <td>
                    {item.cost.toFixed(6)} {currency}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">—</p>
      )}
    </section>
  )
}
