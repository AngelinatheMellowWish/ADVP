import { useEffect, useState } from 'react'

import { errorMessage, type ChartIntent } from '../api/projects'
import { listProviders, type Provider } from '../api/providers'
import {
  correctChartSelection,
  createChartSelection,
  type ChartSelectionResult,
} from '../api/selections'
import { ChartFigure } from './ChartFigure'
import { ExportPanel } from './ExportPanel'

const INTENTS: { value: ChartIntent | ''; label: string }[] = [
  { value: '', label: '自动' },
  { value: 'trend', label: '趋势' },
  { value: 'distribution', label: '分布' },
  { value: 'comparison', label: '比较' },
  { value: 'correlation', label: '相关性' },
  { value: 'composition', label: '构成' },
  { value: 'timeline', label: '时间线' },
]

const DIMENSION_LABELS: Record<string, string> = {
  data_fit: '数据适配',
  perceptual: '视觉感知',
  info_density: '信息密度',
  readability: '可读性',
  performance: '性能',
  accessibility: '可访问性',
  scientific_compliance: '科学合规',
}

export function ChartSelectionPanel({ datasetId }: { datasetId: string }) {
  const [providers, setProviders] = useState<Provider[]>([])
  const [providerId, setProviderId] = useState('')
  const [intent, setIntent] = useState<ChartIntent | ''>('')
  const [result, setResult] = useState<ChartSelectionResult | null>(null)
  const [showFigure, setShowFigure] = useState(false)
  const [correction, setCorrection] = useState('')
  const [correcting, setCorrecting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listProviders()
      .then((items) => {
        if (!cancelled) setProviders(items)
      })
      .catch(() => {
        if (!cancelled) setProviders([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function run() {
    setBusy(true)
    setError(null)
    setShowFigure(false)
    try {
      setResult(
        await createChartSelection(datasetId, {
          intent: intent || undefined,
          provider_id: providerId || undefined,
          max_reselects: 2,
        }),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function applyCorrection() {
    if (!result || !correction.trim()) return
    setCorrecting(true)
    setError(null)
    setShowFigure(false)
    try {
      const corrected = await correctChartSelection(
        result.id,
        correction.trim(),
        providerId || undefined,
      )
      setResult(corrected)
      setCorrection('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setCorrecting(false)
    }
  }

  return (
    <section className="chart-selection" aria-label="AI 选型" data-testid="chart-selection">
      <div className="panel-title">
        <div>
          <h4>
            AI 选型 <span className="badge">规则评分 + 主备</span>
          </h4>
          <p className="muted">
            模型只从规则候选集中选图；后端七维评分决定 Top3，并在低分时重选最多 2 次。
          </p>
        </div>
        <button className="button" onClick={run} disabled={busy}>
          {busy ? '选型中…' : '运行 AI 选型'}
        </button>
      </div>

      <div className="chart-selection-controls">
        <label>
          分析意图
          <select
            value={intent}
            onChange={(event) => setIntent(event.target.value as ChartIntent | '')}
          >
            {INTENTS.map((item) => (
              <option key={item.value || 'auto'} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Provider
          <select value={providerId} onChange={(event) => setProviderId(event.target.value)}>
            <option value="">自动（默认 → 备用）</option>
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
                {provider.is_default ? '（默认）' : ''}
              </option>
            ))}
          </select>
        </label>
      </div>

      {providers.length === 0 ? (
        <p className="muted">未配置 Provider；运行时会降级为规则 Top1。</p>
      ) : null}
      {error ? <p className="error">{error}</p> : null}

      {result ? (
        <div className="chart-selection-result" data-testid="chart-selection-result">
          {result.degraded ? (
            <p className="notice">
              已降级为规则 Top1：{result.degradation_reason ?? 'Provider 不可用'}
            </p>
          ) : null}
          <div className="chart-candidate-head">
            <strong>{result.selected.name.zh}</strong>
            <span className="badge">score {result.selected.score.toFixed(3)}</span>
            {result.selected.confidence !== null ? (
              <span className="badge">confidence {result.selected.confidence.toFixed(2)}</span>
            ) : null}
            <span className="muted">{result.selected.chart_id}</span>
          </div>
          <p>{result.selected.reason}</p>
          <div className="chips">
            {Object.entries(result.selected.fields).map(([role, name]) => (
              <span className="chip" key={role}>
                {role}: {name}
              </span>
            ))}
            {result.selected.aggregation ? (
              <span className="chip">聚合: {result.selected.aggregation}</span>
            ) : null}
            {typeof result.selected.style?.title === 'string' ? (
              <span className="chip">标题: {result.selected.style.title}</span>
            ) : null}
            {typeof result.selected.style?.color === 'string' ? (
              <span className="chip">颜色: {result.selected.style.color}</span>
            ) : null}
            {result.selected.style?.log_x === true || result.selected.style?.log_y === true ? (
              <span className="chip">对数轴</span>
            ) : null}
            {Array.isArray(result.selected.style?.annotations) &&
            result.selected.style.annotations.length > 0 ? (
              <span className="chip">注释 {result.selected.style.annotations.length}</span>
            ) : null}
            {typeof result.selected.style?.legend_position === 'string' ? (
              <span className="chip">图例: {result.selected.style.legend_position}</span>
            ) : null}
            {typeof result.selected.style?.barmode === 'string' ? (
              <span className="chip">柱模式: {result.selected.style.barmode}</span>
            ) : null}
            {result.selected.style?.dual_y === true ? <span className="chip">双轴</span> : null}
            {result.selected.style?.colorblind_palette === true ? (
              <span className="chip">色盲友好</span>
            ) : null}
            {Array.isArray(result.selected.style?.reference_lines) &&
            result.selected.style.reference_lines.length > 0 ? (
              <span className="chip">
                参考线 {result.selected.style.reference_lines.length}
              </span>
            ) : null}
          </div>

          <details className="chart-dependent-details">
            <summary>七维评分</summary>
            <ul>
              {Object.entries(result.selected.dimensions).map(([key, value]) => (
                <li key={key}>
                  {DIMENSION_LABELS[key] ?? key}: {value.toFixed(3)}
                </li>
              ))}
            </ul>
          </details>

          <h4>Top3</h4>
          <ol className="chart-selection-top3">
            {result.top3.map((entry) => (
              <li key={entry.chart_id} className={entry.selected ? 'selected' : ''}>
                <strong>{entry.name.zh}</strong>
                <span className="muted"> · {entry.score.toFixed(3)}</span>
                {entry.selected ? <span className="badge">已选</span> : null}
                <p className="muted">{entry.reason}</p>
              </li>
            ))}
          </ol>

          <p className="muted">
            尝试 {result.attempts} 次 · 重选 {result.reselects} 次 · 输入{' '}
            {result.usage.input_tokens} / 输出 {result.usage.output_tokens} tokens · 估算费用{' '}
            {result.usage.estimated_cost.toFixed(6)} {result.usage.currency}
            {result.provider_name ? ` · ${result.provider_name}` : ' · 规则降级'}
          </p>
          {result.budget?.warning ? (
            <p className="notice">
              预算接近上限：本月 {result.budget.monthly_spend.toFixed(6)}{' '}
              {result.budget.currency}
              {result.budget.monthly_limit
                ? ` / ${result.budget.monthly_limit.toFixed(6)}`
                : ''}
              。
            </p>
          ) : null}
          {result.needs_confirmation ? (
            <p className="notice">分数或 Top1/Top2 差距偏低，请确认 Top3 后再使用。</p>
          ) : null}
          {result.parent_selection_id ? (
            <p className="muted">
              基于选型 {result.parent_selection_id} 修正
              {result.correction_instruction ? `：${result.correction_instruction}` : ''}
            </p>
          ) : null}
          <div className="inline-form">
            <input
              aria-label="修正指令"
              placeholder="例如：换成面积图，强调累计趋势"
              value={correction}
              onChange={(event) => setCorrection(event.target.value)}
            />
            <button
              className="button"
              onClick={applyCorrection}
              disabled={correcting || !correction.trim()}
            >
              应用修正
            </button>
          </div>
          <button className="button" onClick={() => setShowFigure((value) => !value)}>
            {showFigure ? '隐藏图表' : '显示图表'}
          </button>
          {showFigure ? <ChartFigure selectionId={result.id} /> : null}
          <ExportPanel selectionId={result.id} />
        </div>
      ) : null}
    </section>
  )
}
