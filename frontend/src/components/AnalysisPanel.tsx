import { useEffect, useState } from 'react'

import { computeDatasetAnalysis, getDatasetAnalysis, type DatasetAnalysis } from '../api/analysis'
import { errorMessage } from '../api/projects'

export function AnalysisPanel({ datasetId }: { datasetId: string }) {
  const [analysis, setAnalysis] = useState<DatasetAnalysis | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getDatasetAnalysis(datasetId)
      .then((payload) => {
        if (!cancelled) setAnalysis(payload.analysis)
      })
      .catch(() => {
        if (!cancelled) setAnalysis(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [datasetId])

  async function compute() {
    setBusy(true)
    setError(null)
    try {
      setAnalysis((await computeDatasetAnalysis(datasetId)).analysis)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="analysis-panel" aria-label="分析摘要" data-testid="analysis-panel">
      <div className="panel-title">
        <div>
          <h4>
            分析摘要 <span className="badge">规则分析</span>
          </h4>
          <p className="muted">相关性、分布、时间断档与地理范围；基于最多 10,000 行预览。</p>
        </div>
        <button className="button" onClick={compute} disabled={busy}>
          {busy ? '分析中…' : '生成分析摘要'}
        </button>
      </div>

      {loading ? <p className="muted">正在读取分析摘要…</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {!loading && !analysis ? <p className="muted">尚无分析摘要。</p> : null}

      {analysis ? (
        <div className="analysis-result" data-testid="analysis-result">
          <p>{analysis.summary}</p>
          <p className="muted">
            样本 {analysis.sample_size} 行{analysis.sampled ? '（采样）' : ''} · v
            {analysis.version}
          </p>

          {analysis.correlations.length > 0 ? (
            <>
              <h4>相关性</h4>
              <div className="chips">
                {analysis.correlations.map((item) => (
                  <span className="chip" key={`${item.left}-${item.right}`}>
                    {item.left} × {item.right}: r={item.r}
                  </span>
                ))}
              </div>
            </>
          ) : null}

          {analysis.numeric_columns.length > 0 ? (
            <>
              <h4>数值分布</h4>
              <div className="table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>
                      <th>列</th>
                      <th>均值</th>
                      <th>中位数</th>
                      <th>标准差</th>
                      <th>偏度</th>
                      <th>范围</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.numeric_columns.map((column) => (
                      <tr key={column.name}>
                        <td>{column.name}</td>
                        <td>{column.mean}</td>
                        <td>{column.median}</td>
                        <td>{column.std}</td>
                        <td>{column.skewness}</td>
                        <td>
                          {column.min} – {column.max}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}

          {analysis.temporal.length > 0 ? (
            <>
              <h4>时间</h4>
              {analysis.temporal.map((item) => (
                <p className="muted" key={item.name}>
                  {item.name}：{item.start} → {item.end}；最大间隔 {item.max_gap_seconds} 秒
                </p>
              ))}
            </>
          ) : null}

          {analysis.geo ? (
            <>
              <h4>地理范围</h4>
              <p className="muted">
                {analysis.geo.latitude
                  ? `纬度 ${analysis.geo.latitude.min}–${analysis.geo.latitude.max}`
                  : ''}
                {analysis.geo.longitude
                  ? `；经度 ${analysis.geo.longitude.min}–${analysis.geo.longitude.max}`
                  : ''}
              </p>
            </>
          ) : null}

          {analysis.array ? (
            <>
              <h4>数组</h4>
              <p className="muted">
                shape {analysis.array.shape.join(' × ')} · {analysis.array.dtype}
                {analysis.array.units ? ` · ${analysis.array.units}` : ''}
              </p>
            </>
          ) : null}

          <details className="chart-dependent-details">
            <summary>分析说明</summary>
            <ul>
              {analysis.notes.map((note, index) => (
                <li key={`${index}-${note}`}>{note}</li>
              ))}
            </ul>
          </details>
        </div>
      ) : null}
    </section>
  )
}
