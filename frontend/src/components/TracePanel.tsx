import { useEffect, useState } from 'react'

import {
  listPipelineRuns,
  type PipelineRun,
  type PipelineRunSummary,
} from '../api/pipelines'
import { errorMessage } from '../api/projects'
import {
  compareRuns,
  getSelectionCode,
  getTrace,
  rerunPipelineStep,
  type CodeView,
  type RunComparison,
  type TracePayload,
} from '../api/trace'

const ACTIVE_STATUSES = new Set(['pending', 'running', 'paused'])

export function TracePanel({
  run,
  onRunChanged,
}: {
  run: PipelineRun
  onRunChanged: (run: PipelineRun) => void
}) {
  const [trace, setTrace] = useState<TracePayload | null>(null)
  const [runs, setRuns] = useState<PipelineRunSummary[]>([])
  const [compareId, setCompareId] = useState('')
  const [comparison, setComparison] = useState<RunComparison | null>(null)
  const [code, setCode] = useState<CodeView | null>(null)
  const [copied, setCopied] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setCode(null)
    setCopied(false)
    getTrace(run.id)
      .then((payload) => {
        if (!cancelled) setTrace(payload)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
    listPipelineRuns(run.dataset_id)
      .then((items) => {
        if (!cancelled) setRuns(items)
      })
      .catch(() => {
        if (!cancelled) setRuns([])
      })
    return () => {
      cancelled = true
    }
  }, [run.id, run.status, run.dataset_id])

  useEffect(() => {
    if (!trace?.run.parent_run_id) {
      if (!compareId) setComparison(null)
      return
    }
    setCompareId((current) => current || trace.run.parent_run_id || '')
  }, [trace, compareId])

  useEffect(() => {
    let cancelled = false
    if (!compareId) {
      setComparison(null)
      return
    }
    compareRuns(run.id, compareId)
      .then((result) => {
        if (!cancelled) setComparison(result)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [compareId, run.id])

  async function rerun(stepId: string) {
    setBusy(true)
    setError(null)
    try {
      onRunChanged(await rerunPipelineStep(run.id, stepId))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function showCode(selectionId: string) {
    setBusy(true)
    setError(null)
    try {
      setCode(await getSelectionCode(selectionId))
      setCopied(false)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function copyCode() {
    if (!code) return
    try {
      await navigator.clipboard.writeText(code.diff || code.code)
      setCopied(true)
    } catch {
      setError('无法访问剪贴板，请手动选择代码复制')
    }
  }

  return (
    <section className="trace-panel" aria-label="追溯与血缘" data-testid="trace-panel">
      <div className="panel-title">
        <div>
          <h4>
            追溯与血缘 <span className="badge">M6</span>
          </h4>
          <p className="muted">步骤、耗时、模型/Token/费用、数据血缘与旧版本对比。</p>
        </div>
        <div className="inline-form">
          <a className="button" href={`/api/pipeline-runs/${run.id}/trace/export?format=json`}>
            导出 JSON
          </a>
          <a
            className="button"
            href={`/api/pipeline-runs/${run.id}/trace/export?format=markdown`}
          >
            导出 Markdown
          </a>
        </div>
      </div>

      {error ? <p className="error">{error}</p> : null}

      {trace ? (
        <>
          <div className="metrics">
            <span className="metric">
              总耗时 <strong>{trace.summary.duration_ms} ms</strong>
            </span>
            <span className="metric">
              成功/失败{' '}
              <strong>
                {trace.summary.succeeded}/{trace.summary.failed}
              </strong>
            </span>
            <span className="metric">
              模型 <strong>{trace.summary.model ?? '—'}</strong>
            </span>
            <span className="metric">
              Token{' '}
              <strong>
                {trace.summary.input_tokens}/{trace.summary.output_tokens}
              </strong>
            </span>
            <span className="metric">
              费用{' '}
              <strong>
                {trace.summary.estimated_cost.toFixed(6)} {trace.summary.currency}
              </strong>
            </span>
          </div>

          <h4>数据血缘</h4>
          {trace.lineage.length ? (
            <ol className="trace-lineage">
              {trace.lineage.map((item) => (
                <li key={`${item.kind}-${item.id}`}>
                  <span className="badge">{item.kind}</span> {item.name}{' '}
                  <span className="muted">
                    {item.id}
                    {item.row_count !== null ? ` · ${item.row_count}` : ''}
                    {item.sampled ? ' · 采样' : ''}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted">暂无血缘记录。</p>
          )}

          <h4>步骤</h4>
          <ol className="pipeline-steps">
            {trace.nodes.map((node) => (
              <li className={`pipeline-step ${node.status}`} key={node.id}>
                <div className="chart-candidate-head">
                  <strong>{node.name}</strong>
                  <span className="badge">{node.status}</span>
                  <span className="muted">{node.duration_ms} ms</span>
                  <span className="muted">尝试 {node.attempts} 次</span>
                  {node.model ? <span className="muted">{node.model}</span> : null}
                  {node.input_tokens || node.output_tokens ? (
                    <span className="muted">
                      Token {node.input_tokens}/{node.output_tokens}
                    </span>
                  ) : null}
                  {node.estimated_cost ? (
                    <span className="muted">
                      {node.estimated_cost.toFixed(6)} {node.currency}
                    </span>
                  ) : null}
                  {node.selection_id ? (
                    <button
                      className="button"
                      onClick={() => void showCode(node.selection_id ?? '')}
                      disabled={busy}
                    >
                      查看代码
                    </button>
                  ) : null}
                  <button
                    className="button"
                    onClick={() => void rerun(node.id)}
                    disabled={busy || ACTIVE_STATUSES.has(run.status)}
                  >
                    从此步重跑
                  </button>
                </div>
                {node.error ? <p className="error">{node.error}</p> : null}
              </li>
            ))}
          </ol>

          <h4>运行对比</h4>
          <label className="inline-form">
            对比运行
            <select value={compareId} onChange={(event) => setCompareId(event.target.value)}>
              <option value="">不对比</option>
              {runs
                .filter((item) => item.id !== run.id)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id} · {item.status}
                  </option>
                ))}
            </select>
          </label>
          {comparison ? (
            <>
              <p className="muted">
                对比运行 {comparison.left_run_id} · {comparison.left_status} ·{' '}
                {comparison.left_duration_ms} ms · {comparison.left_cost.toFixed(6)}
              </p>
              <div className="table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>
                      <th>步骤</th>
                      <th>对比状态</th>
                      <th>当前状态</th>
                      <th>耗时差</th>
                      <th>费用差</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.steps.map((item) => (
                      <tr key={item.key}>
                        <td>{item.key}</td>
                        <td>{item.left.status ?? '—'}</td>
                        <td>{item.right.status ?? '—'}</td>
                        <td>{item.duration_delta_ms} ms</td>
                        <td>{item.cost_delta.toFixed(6)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}

          {code ? (
            <div className="trace-code" data-testid="trace-code">
              <div className="chart-candidate-head">
                <h4>生成代码 {code.parent_selection_id ? '与差异' : ''}</h4>
                <a
                  className="button"
                  href={`/api/chart-selections/${code.selection_id}/export/python`}
                >
                  下载 Python
                </a>
                <button className="button" onClick={() => void copyCode()}>
                  {copied ? '已复制' : '复制代码'}
                </button>
                <button className="button" onClick={() => setCode(null)}>
                  收起
                </button>
              </div>
              <pre className="json-preview">{code.diff || code.code}</pre>
            </div>
          ) : null}
        </>
      ) : (
        <p className="muted">正在加载追溯信息…</p>
      )}
    </section>
  )
}
