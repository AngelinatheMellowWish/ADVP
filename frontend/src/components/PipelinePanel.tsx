import { useEffect, useState } from 'react'

import type { CleanStep } from '../api/cleaning'
import { errorMessage, type ChartIntent } from '../api/projects'
import { listProviders, type Provider } from '../api/providers'
import {
  createReportExport,
  getExportJob,
  retryExportJob,
  type ExportJob,
} from '../api/exportJobs'
import {
  cancelPipelineRun,
  createPipelineRun,
  getPipelineRun,
  listPipelineRuns,
  pausePipelineRun,
  regeneratePipelineReport,
  resumePipelineRun,
  retryPipelineStep,
  type PipelineRun,
} from '../api/pipelines'
import { TracePanel } from './TracePanel'

const INTENTS: { value: ChartIntent | ''; label: string }[] = [
  { value: '', label: '自动' },
  { value: 'trend', label: '趋势' },
  { value: 'distribution', label: '分布' },
  { value: 'comparison', label: '比较' },
  { value: 'correlation', label: '相关性' },
  { value: 'composition', label: '构成' },
  { value: 'timeline', label: '时间线' },
]

const ACTIVE_STATUSES = new Set(['pending', 'running'])

export function PipelinePanel({ datasetId }: { datasetId: string }) {
  const [providers, setProviders] = useState<Provider[]>([])
  const [providerId, setProviderId] = useState('')
  const [intent, setIntent] = useState<ChartIntent | ''>('')
  const [cleanStepsText, setCleanStepsText] = useState('')
  const [confirmHighRisk, setConfirmHighRisk] = useState(false)
  const [run, setRun] = useState<PipelineRun | null>(null)
  const [reportLanguage, setReportLanguage] = useState<'zh' | 'en'>('zh')
  const [reportTemplate, setReportTemplate] = useState<'standard' | 'compact'>('standard')
  const [reportConclusion, setReportConclusion] = useState('')
  const [includeChart, setIncludeChart] = useState(true)
  const [exportJob, setExportJob] = useState<ExportJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([listProviders(), listPipelineRuns(datasetId)])
      .then(async ([providerItems, runs]) => {
        if (cancelled) return
        setProviders(providerItems)
        if (runs.length > 0) {
          setRun(await getPipelineRun(runs[0].id))
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [datasetId])

  useEffect(() => {
    if (!run || !ACTIVE_STATUSES.has(run.status)) return
    const timer = window.setInterval(() => {
      getPipelineRun(run.id)
        .then(setRun)
        .catch((err: unknown) => setError(errorMessage(err)))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [run])

  useEffect(() => {
    if (!exportJob || ['succeeded', 'failed', 'cancelled'].includes(exportJob.status)) return
    const timer = window.setInterval(() => {
      getExportJob(exportJob.id)
        .then(setExportJob)
        .catch((err: unknown) => setError(errorMessage(err)))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [exportJob])

  useEffect(() => {
    if (!exportJob) return
    if (!['succeeded', 'failed'].includes(exportJob.status)) return
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
    new Notification(
      exportJob.status === 'succeeded' ? 'ADVP 导出完成' : 'ADVP 导出失败',
      {
        body:
          exportJob.status === 'succeeded'
            ? `${exportJob.format.toUpperCase()} 已生成`
            : exportJob.error ?? '请查看导出任务状态',
      },
    )
  }, [exportJob?.id, exportJob?.status, exportJob?.format, exportJob?.error, exportJob])

  async function start() {
    setBusy(true)
    setError(null)
    let cleanSteps: CleanStep[] = []
    if (cleanStepsText.trim()) {
      try {
        const parsed = JSON.parse(cleanStepsText) as unknown
        if (!Array.isArray(parsed)) throw new Error('recipe must be an array')
        cleanSteps = parsed as CleanStep[]
      } catch {
        setError('清洗配方必须是 JSON 数组。')
        setBusy(false)
        return
      }
    }
    try {
      setRun(
        await createPipelineRun(datasetId, {
          intent: intent || undefined,
          provider_id: providerId || undefined,
          max_reselects: 2,
          clean_steps: cleanSteps,
          confirm_high_risk: confirmHighRisk,
          report_language: reportLanguage,
          report_template: reportTemplate,
          report_conclusion: reportConclusion.trim() || null,
          report_include_chart: includeChart,
        }),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function act(action: 'pause' | 'resume' | 'cancel') {
    if (!run) return
    setBusy(true)
    setError(null)
    try {
      const next =
        action === 'pause'
          ? await pausePipelineRun(run.id)
          : action === 'resume'
            ? await resumePipelineRun(run.id)
            : await cancelPipelineRun(run.id)
      setRun(next)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function retryFailed() {
    if (!run) return
    const failed = run.steps.find((step) => step.status === 'failed')
    if (!failed) return
    setBusy(true)
    setError(null)
    try {
      setRun(await retryPipelineStep(run.id, failed.id))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function regenerate() {
    if (!run) return
    setBusy(true)
    setError(null)
    try {
      const result = await regeneratePipelineReport(run.id, {
        language: reportLanguage,
        template: reportTemplate,
        conclusion: reportConclusion.trim() || null,
        include_chart: includeChart,
      })
      setRun(result.run)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function startExport(format: 'html' | 'pdf') {
    if (!run) return
    setBusy(true)
    setError(null)
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      void Notification.requestPermission()
    }
    try {
      setExportJob(await createReportExport(run.id, format))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function retryExport() {
    if (!exportJob) return
    setBusy(true)
    setError(null)
    try {
      setExportJob(await retryExportJob(exportJob.id))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="pipeline-panel" aria-label="分析管线" data-testid="pipeline-panel">
      <div className="panel-title">
        <div>
          <h4>
            分析管线 <span className="badge">BackgroundTasks + 轮询</span>
          </h4>
          <p className="muted">
            画像 → 规则候选 → AI 选型 → 渲染占位 → 报告占位。暂停/取消在当前步骤结束后生效。
          </p>
        </div>
        <button className="button" onClick={start} disabled={busy}>
          运行管线
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
              </option>
            ))}
          </select>
        </label>
        <label className="pipeline-clean-input">
          清洗配方 JSON（可选）
          <textarea
            rows={2}
            placeholder='[{"operation":"drop_missing","columns":["age"]}]'
            value={cleanStepsText}
            onChange={(event) => setCleanStepsText(event.target.value)}
          />
        </label>
        <label>
          报告语言
          <select
            value={reportLanguage}
            onChange={(event) => setReportLanguage(event.target.value as 'zh' | 'en')}
          >
            <option value="zh">中文</option>
            <option value="en">English</option>
          </select>
        </label>
        <label>
          报告模板
          <select
            value={reportTemplate}
            onChange={(event) =>
              setReportTemplate(event.target.value as 'standard' | 'compact')
            }
          >
            <option value="standard">标准</option>
            <option value="compact">紧凑</option>
          </select>
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={includeChart}
            onChange={(event) => setIncludeChart(event.target.checked)}
          />
          嵌入图表截图
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={confirmHighRisk}
            onChange={(event) => setConfirmHighRisk(event.target.checked)}
          />
          确认高风险清洗
        </label>
        <label className="pipeline-clean-input">
          报告结论（可选）
          <textarea
            rows={2}
            placeholder="留空时使用自动结论"
            value={reportConclusion}
            onChange={(event) => setReportConclusion(event.target.value)}
          />
        </label>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {!run ? <p className="muted">尚未运行管线。</p> : null}

      {run ? (
        <div className="pipeline-run" data-testid="pipeline-run">
          <div className="chart-candidate-head">
            <strong>{run.status}</strong>
            {run.current_step ? <span className="badge">{run.current_step}</span> : null}
            <span className="muted">{run.id}</span>
          </div>
          {run.error ? <p className="error">{run.error}</p> : null}
          <div className="inline-form">
            {ACTIVE_STATUSES.has(run.status) ? (
              <button className="button" onClick={() => act('pause')} disabled={busy}>
                暂停
              </button>
            ) : null}
            {run.status === 'paused' ? (
              <button className="button" onClick={() => act('resume')} disabled={busy}>
                恢复
              </button>
            ) : null}
            {run.status === 'failed' ? (
              <button className="button" onClick={retryFailed} disabled={busy}>
                重试失败步骤
              </button>
            ) : null}
            {!['succeeded', 'failed', 'cancelled'].includes(run.status) ? (
              <button className="button" onClick={() => act('cancel')} disabled={busy}>
                取消
              </button>
            ) : null}
            {run.steps.some((step) => step.key === 'report' && step.status === 'succeeded') ? (
              <>
                <a className="button" href={`/api/pipeline-runs/${run.id}/report?format=md`}>
                  Markdown
                </a>
                <a className="button" href={`/api/pipeline-runs/${run.id}/report?format=html`}>
                  HTML
                </a>
                <a className="button" href={`/api/pipeline-runs/${run.id}/report?format=pdf`}>
                  PDF
                </a>
                <button className="button" onClick={() => void regenerate()} disabled={busy}>
                  重新生成报告
                </button>
                <button
                  className="button"
                  onClick={() => void startExport('pdf')}
                  disabled={busy || exportJob?.status === 'running'}
                >
                  后台导出 PDF
                </button>
              </>
            ) : null}
          </div>

          {exportJob ? (
            <p
              className={exportJob.status === 'succeeded' ? 'notice' : 'muted'}
              data-testid="export-job-status"
            >
              导出任务：{exportJob.status} · 尝试 {exportJob.attempts}
              {exportJob.error ? ` · ${exportJob.error}` : ''}
              {exportJob.download_url ? (
                <>
                  {' '}
                  <a className="button" href={exportJob.download_url}>
                    下载
                  </a>
                </>
              ) : null}
              {exportJob.status === 'failed' ? (
                <button className="button" onClick={() => void retryExport()} disabled={busy}>
                  重试导出
                </button>
              ) : null}
            </p>
          ) : null}

          <ol className="pipeline-steps">
            {run.steps.map((step) => (
              <li className={`pipeline-step ${step.status}`} key={step.id}>
                <div className="chart-candidate-head">
                  <strong>{step.name}</strong>
                  <span className="badge">{step.status}</span>
                  {step.placeholder ? <span className="badge">占位</span> : null}
                  <span className="muted">尝试 {step.attempts} 次</span>
                </div>
                {step.error ? <p className="error">{step.error}</p> : null}
                {Object.keys(step.output).length > 0 ? (
                  <pre className="json-preview">{JSON.stringify(step.output, null, 2)}</pre>
                ) : null}
              </li>
            ))}
          </ol>

          <TracePanel run={run} onRunChanged={setRun} />
        </div>
      ) : null}
    </section>
  )
}
