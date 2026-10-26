import { useEffect, useState } from 'react'

import {
  getBudget,
  getCostSummary,
  updateBudget,
  type BudgetStatus,
  type CostSummary,
} from '../api/costs'
import { errorMessage } from '../api/projects'

export function CostPanel({ projectId }: { projectId: string }) {
  const [budget, setBudget] = useState<BudgetStatus | null>(null)
  const [cost, setCost] = useState<CostSummary | null>(null)
  const [projectLimit, setProjectLimit] = useState('')
  const [monthlyLimit, setMonthlyLimit] = useState('')
  const [warningRatio, setWarningRatio] = useState('0.8')
  const [currency, setCurrency] = useState('USD')
  const [period, setPeriod] = useState<'month' | 'all'>('month')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([getBudget(projectId), getCostSummary(projectId, period)])
      .then(([budgetValue, costValue]) => {
        if (cancelled) return
        setBudget(budgetValue)
        setCost(costValue)
        setProjectLimit(budgetValue.project_limit?.toString() ?? '')
        setMonthlyLimit(budgetValue.monthly_limit?.toString() ?? '')
        setWarningRatio(budgetValue.warning_ratio.toString())
        setCurrency(budgetValue.currency)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [projectId, period])

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const next = await updateBudget(projectId, {
        project_limit: projectLimit.trim() ? Number(projectLimit) : null,
        monthly_limit: monthlyLimit.trim() ? Number(monthlyLimit) : null,
        warning_ratio: Number(warningRatio),
        currency: currency.trim() || 'USD',
      })
      setBudget(next)
      setCost(await getCostSummary(projectId, period))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel cost-panel" aria-label="成本与预算" data-testid="cost-panel">
      <div className="panel-title">
        <div>
          <h3>
            成本与预算 <span className="badge">项目级 / 月度</span>
          </h3>
          <p className="muted">费用按 Provider/model 价格估算，不代表供应商账单；达到上限后 AI 选型降级为规则 Top1。</p>
        </div>
        <div className="inline-form">
          <label>
            周期
            <select
              value={period}
              onChange={(event) => setPeriod(event.target.value as 'month' | 'all')}
            >
              <option value="month">本月</option>
              <option value="all">全部</option>
            </select>
          </label>
          <a className="button" href={`/api/projects/${projectId}/costs.csv?period=${period}`}>
            导出 CSV
          </a>
          <a className="button" href="/api/diagnostics/bundle">
            诊断包
          </a>
        </div>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {budget?.warning ? (
        <p className="notice">
          预算接近上限：本月 {budget.monthly_spend.toFixed(6)} /{' '}
          {budget.monthly_limit?.toFixed(6) ?? '未设置'} {budget.currency}
        </p>
      ) : null}
      {budget?.exceeded ? (
        <p className="notice">预算已超限：AI 选型将降级为规则 Top1（{budget.reason}）。</p>
      ) : null}

      <div className="metrics">
        <span className="metric">
          总费用 <strong>{cost ? cost.total_cost.toFixed(6) : '—'} {cost?.currency ?? ''}</strong>
        </span>
        <span className="metric">
          输入 Token <strong>{cost?.input_tokens ?? '—'}</strong>
        </span>
        <span className="metric">
          输出 Token <strong>{cost?.output_tokens ?? '—'}</strong>
        </span>
        <span className="metric">
          请求数 <strong>{cost ? cost.by_provider.reduce((sum, item) => sum + item.requests, 0) : '—'}</strong>
        </span>
        <span className="metric">
          重选/重试费用 <strong>{cost ? cost.retry_cost.toFixed(6) : '—'}</strong>
        </span>
      </div>

      <div className="cost-grid">
        <div>
          <h4>按 Provider</h4>
          {cost?.by_provider.length ? (
            <ul className="cost-list">
              {cost.by_provider.map((item) => (
                <li key={item.name}>
                  <span>{item.name}</span>
                  <span>
                    {item.cost.toFixed(6)} · {item.requests} 次
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">暂无请求。</p>
          )}
        </div>
        <div>
          <h4>按模型</h4>
          {cost?.by_model.length ? (
            <ul className="cost-list">
              {cost.by_model.map((item) => (
                <li key={item.name}>
                  <span>{item.name}</span>
                  <span>
                    {item.cost.toFixed(6)} · {item.requests} 次
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">暂无请求。</p>
          )}
        </div>
        <div>
          <h4>按操作标签</h4>
          {cost?.by_tag?.length ? (
            <ul className="cost-list">
              {cost.by_tag.map((item) => (
                <li key={item.name}>
                  <span>{item.name}</span>
                  <span>
                    {item.cost.toFixed(6)} · {item.requests} 次
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">暂无请求。</p>
          )}
        </div>
        <div>
          <h4>按任务运行</h4>
          {cost?.by_run?.length ? (
            <ul className="cost-list">
              {cost.by_run.map((item) => (
                <li key={item.name}>
                  <span>{item.name}</span>
                  <span>
                    {item.cost.toFixed(6)} · {item.requests} 次
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">暂无请求。</p>
          )}
        </div>
        <div>
          <h4>按图表</h4>
          {cost?.by_chart?.length ? (
            <ul className="cost-list">
              {cost.by_chart.map((item) => (
                <li key={item.name}>
                  <span>{item.name}</span>
                  <span>
                    {item.cost.toFixed(6)} · {item.requests} 次
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">暂无请求。</p>
          )}
        </div>
      </div>

      <h4>预算设置</h4>
      <div className="cleaning-form">
        <label>
          项目上限
          <input
            value={projectLimit}
            onChange={(event) => setProjectLimit(event.target.value)}
            placeholder="留空表示不限"
          />
        </label>
        <label>
          月度上限
          <input
            value={monthlyLimit}
            onChange={(event) => setMonthlyLimit(event.target.value)}
            placeholder="留空表示不限"
          />
        </label>
        <label>
          警告比例
          <input
            value={warningRatio}
            onChange={(event) => setWarningRatio(event.target.value)}
          />
        </label>
        <label>
          货币
          <input value={currency} onChange={(event) => setCurrency(event.target.value)} />
        </label>
        <button className="button" onClick={save} disabled={busy}>
          保存预算
        </button>
      </div>
    </section>
  )
}
