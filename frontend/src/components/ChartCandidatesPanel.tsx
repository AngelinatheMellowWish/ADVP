import { useEffect, useState } from 'react'

import {
  errorMessage,
  fetchChartCandidates,
  type ChartCandidatesResponse,
  type ChartIntent,
} from '../api/projects'

const INTENTS: { value: ChartIntent | ''; label: string }[] = [
  { value: '', label: '自动' },
  { value: 'trend', label: '趋势' },
  { value: 'distribution', label: '分布' },
  { value: 'comparison', label: '比较' },
  { value: 'correlation', label: '相关性' },
  { value: 'composition', label: '构成' },
  { value: 'timeline', label: '时间线' },
]

export function ChartCandidatesPanel({
  datasetId,
  datasetKind,
}: {
  datasetId: string
  datasetKind: string
}) {
  const [intent, setIntent] = useState<ChartIntent | ''>('')
  const [data, setData] = useState<ChartCandidatesResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchChartCandidates(datasetId, intent || undefined)
      .then((payload) => {
        if (!cancelled) setData(payload)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setData(null)
          setError(errorMessage(err))
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [datasetId, intent, reloadKey])

  return (
    <section className="chart-candidates" aria-label="图表候选" data-testid="chart-candidates">
      <div className="panel-title">
        <div>
          <h4>
            图表候选 <span className="badge">规则预览，临时</span>
          </h4>
          <p className="muted">
            {datasetKind === 'array'
              ? '数值数组按维度生成热图/切片候选；3D 数组默认沿第一维切片。'
              : '按字段类型、基数、行数与分析意图硬筛；候选集外图表不会被选择。'}
          </p>
        </div>
        <button className="button" onClick={() => setReloadKey((value) => value + 1)}>
          刷新候选
        </button>
      </div>

      <label className="chart-intent">
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

      {loading ? <p className="muted">正在生成候选…</p> : null}
      {error ? <p className="error">{error}</p> : null}

      {data && !loading ? (
        <>
          <p className="muted">
            registry v{data.registry_version} · {data.candidates.length} 个候选 ·{' '}
            {data.excluded.length} 个排除
          </p>
          {data.candidates.length === 0 ? (
            <p className="muted">没有符合条件的图表。可调整意图或先处理质量问题。</p>
          ) : (
            <ul className="chart-candidate-list">
              {data.candidates.map((candidate) => (
                <li className="chart-candidate" key={candidate.id}>
                  <div className="chart-candidate-head">
                    <strong>{candidate.name.zh}</strong>
                    <span className="badge">#{candidate.rule_rank}</span>
                    <span className="muted">
                      {candidate.family} · {candidate.backend}
                    </span>
                  </div>
                  <p>{candidate.why}</p>
                  <div className="chips">
                    {Object.entries(candidate.suggested_fields).map(([role, name]) => (
                      <span className="chip" key={role}>
                        {role}: {name}
                      </span>
                    ))}
                    {candidate.array_mapping ? (
                      <span className="chip">
                        切片：
                        {candidate.array_mapping.slice_axis
                          ? `${candidate.array_mapping.slice_axis}=${candidate.array_mapping.slice_index}`
                          : '无'}{' '}
                        · {candidate.array_mapping.display_shape.join('×')}
                      </span>
                    ) : null}
                  </div>
                  <p className="muted">{candidate.notes}</p>
                </li>
              ))}
            </ul>
          )}
          {data.excluded.length > 0 ? (
            <details className="chart-excluded">
              <summary>排除原因（{data.excluded.length}）</summary>
              <ul>
                {data.excluded.map((item) => (
                  <li key={item.id}>
                    <strong>{item.id}</strong> <span className="muted">{item.reason_code}</span>{' '}
                    {item.message}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  )
}
