import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { buildChartSelection } from '../api/charts'
import {
  errorMessage,
  fetchChartCandidates,
  getDataset,
  type ChartCandidatesResponse,
  type DatasetDetail,
} from '../api/projects'
import { listProviders, type Provider } from '../api/providers'
import {
  cancelPipelineRun,
  createPipelineRun,
  getPipelineRun,
  listPipelineRuns,
  pausePipelineRun,
  resumePipelineRun,
  retryPipelineStep,
  type PipelineRun,
  type PipelineStep,
} from '../api/pipelines'
import {
  subscribePipelineEvents,
  type PipelineEvent,
} from '../api/pipelineEvents'
import {
  correctChartSelection,
  getChartSelection,
  type ChartSelectionResult,
} from '../api/selections'
import { useProject } from '../app/projectContext'
import { ChartFigure } from '../components/ChartFigure'
import { PipelineEventLog } from '../components/PipelineEventLog'
import { PipelineTimeline, type TimelineStep } from '../components/PipelineTimeline'

const STEP_KEYS = [
  'extract',
  'profile',
  'clean',
  'candidates',
  'analyze',
  'selection',
  'render',
  'report',
] as const

const ACTIVE_STATUSES = new Set(['pending', 'running'])
const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'cancelled'])

type Intent = 'trend' | 'distribution' | 'comparison' | 'correlation' | 'composition' | 'timeline'

const INTENTS: Intent[] = [
  'trend',
  'distribution',
  'comparison',
  'correlation',
  'composition',
  'timeline',
]

function stepStatusFromEvent(type: string): string | null {
  if (type === 'step_started') return 'running'
  if (type === 'step_succeeded') return 'succeeded'
  if (type === 'step_failed') return 'failed'
  return null
}

function runStatusFromEvent(type: string): string | null {
  if (type === 'run_started') return 'running'
  if (type === 'run_succeeded') return 'succeeded'
  if (type === 'run_failed') return 'failed'
  if (type === 'run_paused') return 'paused'
  if (type === 'run_cancelled') return 'cancelled'
  return null
}

function outputValue(step: PipelineStep | undefined, key: string): string | null {
  const value = step?.output?.[key]
  return typeof value === 'string' ? value : null
}

export function P04Pipeline() {
  const { t } = useTranslation()
  const { projectId } = useParams<{ projectId?: string }>()
  const { project } = useProject()
  const [params, setParams] = useSearchParams()
  const datasetId = params.get('dataset') ?? project?.datasets[0]?.id ?? null
  const runParam = params.get('run')

  const [dataset, setDataset] = useState<DatasetDetail | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [run, setRun] = useState<PipelineRun | null>(null)
  const [events, setEvents] = useState<PipelineEvent[]>([])
  const [stepOverrides, setStepOverrides] = useState<Record<string, string>>({})
  const [statusOverride, setStatusOverride] = useState<string | null>(null)
  const [selection, setSelection] = useState<ChartSelectionResult | null>(null)
  const [activeStep, setActiveStep] = useState<string>('extract')
  const [intent, setIntent] = useState<Intent | ''>('')
  const [providerId, setProviderId] = useState('')
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [streamError, setStreamError] = useState(false)
  const [top3Open, setTop3Open] = useState(false)
  const [candidates, setCandidates] = useState<ChartCandidatesResponse | null>(null)
  const [correction, setCorrection] = useState('')
  const [correcting, setCorrecting] = useState(false)

  useEffect(() => {
    if (!datasetId) {
      setDataset(null)
      return
    }
    let cancelled = false
    getDataset(datasetId)
      .then((value) => {
        if (!cancelled) setDataset(value)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
    return () => {
      cancelled = true
    }
  }, [datasetId])

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

  useEffect(() => {
    if (!datasetId) {
      setRun(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    async function load() {
      try {
        if (runParam) {
          const value = await getPipelineRun(runParam)
          if (!cancelled) setRun(value)
          return
        }
        const runs = await listPipelineRuns(datasetId as string)
        if (cancelled) return
        if (runs.length === 0) {
          setRun(null)
          return
        }
        const value = await getPipelineRun(runs[0].id)
        if (!cancelled) setRun(value)
      } catch (caught) {
        if (!cancelled) setError(errorMessage(caught))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [datasetId, runParam])

  useEffect(() => {
    setEvents([])
    setStepOverrides({})
    setStatusOverride(null)
    setSelection(null)
  }, [run?.id])

  useEffect(() => {
    if (run?.current_step) setActiveStep(run.current_step)
  }, [run?.current_step])

  const selectionId = useMemo(() => {
    const step = run?.steps.find((item) => item.key === 'selection')
    return outputValue(step, 'selection_id')
  }, [run])

  useEffect(() => {
    if (!selectionId) {
      setSelection(null)
      return
    }
    let cancelled = false
    getChartSelection(selectionId)
      .then((value) => {
        if (!cancelled) setSelection(value)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
    return () => {
      cancelled = true
    }
  }, [selectionId])

  useEffect(() => {
    const runId = run?.id
    if (!runId) return
    let disposed = false
    let lastSeq = 0
    let closeStream: (() => void) | null = null
    let retry: number | undefined
    let poll: number | undefined

    async function refresh() {
      try {
        const value = await getPipelineRun(runId as string)
        if (disposed) return
        setRun(value)
        if (TERMINAL_STATUSES.has(value.status)) {
          stopPolling()
          closeStream?.()
          closeStream = null
        }
      } catch {
        // The SSE stream or the next poll retries; keep the last known state.
      }
    }

    function stopPolling() {
      if (poll !== undefined) {
        window.clearInterval(poll)
        poll = undefined
      }
    }

    function startPolling() {
      if (poll !== undefined) return
      poll = window.setInterval(() => void refresh(), 1000)
    }

    function apply(event: PipelineEvent) {
      lastSeq = Math.max(lastSeq, event.seq)
      setEvents((current) =>
        current.some((item) => item.seq === event.seq)
          ? current
          : [...current, event].sort((a, b) => a.seq - b.seq),
      )
      const key = event.payload.key
      const stepStatus = stepStatusFromEvent(event.type)
      if (stepStatus && typeof key === 'string') {
        setStepOverrides((current) => ({ ...current, [key]: stepStatus }))
        setActiveStep(key)
      }
      const nextStatus = runStatusFromEvent(event.type)
      if (nextStatus) setStatusOverride(nextStatus)
      if (TERMINAL_STATUSES.has(nextStatus ?? '')) {
        void refresh()
      }
    }

    function connect() {
      closeStream?.()
      closeStream = subscribePipelineEvents(
        runId as string,
        lastSeq,
        apply,
        () => {
          setStreamError(true)
          startPolling()
          closeStream?.()
          closeStream = null
          if (retry !== undefined) window.clearTimeout(retry)
          retry = window.setTimeout(() => {
            stopPolling()
            setStreamError(false)
            connect()
          }, 3000)
        },
      )
    }

    connect()
    return () => {
      disposed = true
      closeStream?.()
      stopPolling()
      if (retry !== undefined) window.clearTimeout(retry)
    }
  }, [run?.id])

  const runStatus = statusOverride ?? run?.status ?? 'idle'

  const timelineSteps = useMemo<TimelineStep[]>(() => {
    const byKey = new Map(run?.steps.map((step) => [step.key, step]) ?? [])
    return STEP_KEYS.map((key) => {
      const step = byKey.get(key)
      return {
        key,
        status:
          key === 'extract' ? 'succeeded' : (stepOverrides[key] ?? step?.status ?? 'pending'),
        attempts: step?.attempts,
      }
    })
  }, [run, stepOverrides])

  const selectedStep = run?.steps.find((step) => step.key === activeStep)
  const failedStep = run?.steps.find((step) => step.status === 'failed')
  const estimatedCost = selection?.usage.estimated_cost ?? 0

  function updateParams(nextRunId?: string | null) {
    if (!datasetId) return
    const next = new URLSearchParams(params)
    next.set('dataset', datasetId)
    if (nextRunId) next.set('run', nextRunId)
    else next.delete('run')
    setParams(next)
  }

  async function startRun() {
    if (!datasetId) return
    setBusy(true)
    setError(null)
    try {
      const value = await createPipelineRun(datasetId, {
        intent: intent || undefined,
        provider_id: providerId || undefined,
      })
      setRun(value)
      updateParams(value.id)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function act(action: 'pause' | 'resume' | 'cancel') {
    if (!run) return
    setBusy(true)
    setError(null)
    try {
      const value =
        action === 'pause'
          ? await pausePipelineRun(run.id)
          : action === 'resume'
            ? await resumePipelineRun(run.id)
            : await cancelPipelineRun(run.id)
      setRun(value)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function retryFailed() {
    if (!run || !failedStep) return
    setBusy(true)
    setError(null)
    try {
      setRun(await retryPipelineStep(run.id, failedStep.id))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function applyCorrection() {
    if (!selection || !correction.trim()) return
    setCorrecting(true)
    setError(null)
    try {
      setSelection(
        await correctChartSelection(selection.id, correction.trim(), providerId || undefined),
      )
      setCorrection('')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setCorrecting(false)
    }
  }

  async function openTop3() {
    setTop3Open(true)
    if (!candidates && datasetId) {
      try {
        setCandidates(await fetchChartCandidates(datasetId))
      } catch {
        setCandidates(null)
      }
    }
  }

  async function chooseChart(chartId: string) {
    if (!datasetId || !selection) return
    setBusy(true)
    setError(null)
    try {
      let available = candidates
      if (!available) {
        available = await fetchChartCandidates(datasetId)
        setCandidates(available)
      }
      const candidate = available.candidates.find((item) => item.id === chartId)
      if (!candidate) throw new Error(t('pipelinePage.candidateMissing'))
      setSelection(
        await buildChartSelection(datasetId, {
          chart_id: chartId,
          fields: candidate.suggested_fields,
          reason: t('pipelinePage.top3Reason', { name: candidate.name.zh }),
          parent_selection_id: selection.id,
        }),
      )
      setTop3Open(false)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  if (!datasetId) {
    return (
      <section className="page pipeline-page" data-testid="page-p04">
        <h1>{t('pipelinePage.title')}</h1>
        <p className="muted">{t('pipelinePage.missingDataset')}</p>
        {project && project.datasets.length > 0 ? (
          <ul className="file-list">
            {project.datasets.map((item) => (
              <li key={item.id}>
                <span>{item.name}</span>
                <Link
                  className="btn"
                  to={`/projects/${projectId}/pipeline?dataset=${item.id}`}
                >
                  {t('pipelinePage.selectDataset')}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    )
  }

  return (
    <section className="page pipeline-page" data-testid="page-p04">
      <header className="pipeline-head">
        <div>
          <h1>{dataset?.name ?? t('pipelinePage.title')}</h1>
          <p className="muted">
            {t('pipelinePage.source')}: {dataset?.format ?? '—'} ·{' '}
            {t('pipelinePage.startedAt')}:{' '}
            {run?.started_at ? new Date(run.started_at).toLocaleString() : '—'} ·{' '}
            {t('pipelinePage.estimatedCost')}: {estimatedCost.toFixed(6)}
          </p>
        </div>
        <div className="pipeline-head-status">
          <span className={`status-pill status-${runStatus}`}>
            {t(`pipelinePage.status.${runStatus}`, { defaultValue: runStatus })}
          </span>
          {run ? <span className="muted">{run.current_step ?? run.id}</span> : null}
        </div>
      </header>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {streamError ? <p className="notice">{t('pipelinePage.eventStreamError')}</p> : null}
      {loading ? <p className="muted">{t('pipelinePage.loading')}</p> : null}

      <div className="pipeline-layout">
        <div className="pipeline-main">
          <section className="card">
            <div className="pipeline-run-head">
              <div>
                <h2>{t('pipelinePage.timeline')}</h2>
                <p className="muted">{t('pipelinePage.extractHint')}</p>
              </div>
              <div className="inline-form">
                {run && ACTIVE_STATUSES.has(run.status) ? (
                  <button className="btn" type="button" onClick={() => void act('pause')}>
                    {t('pipelinePage.pause')}
                  </button>
                ) : null}
                {run?.status === 'paused' ? (
                  <button className="btn" type="button" onClick={() => void act('resume')}>
                    {t('pipelinePage.resume')}
                  </button>
                ) : null}
                {run?.status === 'failed' && failedStep ? (
                  <button className="btn" type="button" onClick={() => void retryFailed()}>
                    {t('pipelinePage.retry')}
                  </button>
                ) : null}
                {run && !TERMINAL_STATUSES.has(run.status) ? (
                  <button className="btn" type="button" onClick={() => void act('cancel')}>
                    {t('pipelinePage.cancel')}
                  </button>
                ) : null}
              </div>
            </div>
            <PipelineTimeline
              steps={timelineSteps}
              activeKey={activeStep}
              onSelect={setActiveStep}
            />
            <div className="pipeline-actions">
              {selectionId ? (
                <>
                  <Link
                    className="btn home-primary"
                    to={`/projects/${projectId}/charts?dataset=${datasetId}`}
                  >
                    {t('pipelinePage.openCharts')}
                  </Link>
                  <Link className="btn" to={`/projects/${projectId}/scene?dataset=${datasetId}`}>
                    {t('pipelinePage.openScene')}
                  </Link>
                  <Link className="btn" to={`/projects/${projectId}/reports?dataset=${datasetId}`}>
                    {t('pipelinePage.openReports')}
                  </Link>
                </>
              ) : null}
            </div>
          </section>

          <PipelineEventLog events={events} />

          <section className="card pipeline-run-options">
            <h2>{run ? t('pipelinePage.newRun') : t('pipelinePage.runOptions')}</h2>
            <div className="pipeline-options-grid">
              <label>
                {t('pipelinePage.intent')}
                <select
                  className="input"
                  value={intent}
                  onChange={(event) => setIntent(event.target.value as Intent | '')}
                >
                  <option value="">{t('pipelinePage.auto')}</option>
                  {INTENTS.map((value) => (
                    <option key={value} value={value}>
                      {t(`pipelinePage.intents.${value}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t('pipelinePage.provider')}
                <select
                  className="input"
                  value={providerId}
                  onChange={(event) => setProviderId(event.target.value)}
                >
                  <option value="">{t('pipelinePage.providerAuto')}</option>
                  {providers.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <button
              className="btn home-primary"
              type="button"
              onClick={() => void startRun()}
              disabled={busy || (run !== null && ACTIVE_STATUSES.has(run.status))}
            >
              {busy ? t('pipelinePage.starting') : t('pipelinePage.run')}
            </button>
            {!run && !loading ? (
              <p className="muted">{t('pipelinePage.noRuns')}</p>
            ) : null}
          </section>
        </div>

        <aside className="pipeline-side">
          <section className="card">
            <h2>{t('pipelinePage.detail')}</h2>
            <p className="muted">
              {t(`pipelinePage.steps.${activeStep}`)} ·{' '}
              {selectedStep
                ? t(`pipelinePage.status.${stepOverrides[activeStep] ?? selectedStep.status}`, {
                    defaultValue: stepOverrides[activeStep] ?? selectedStep.status,
                  })
                : t('pipelinePage.status.succeeded')}
            </p>
            {selectedStep?.error ? <p className="error-text">{selectedStep.error}</p> : null}
            {selectedStep ? (
              <>
                <p className="muted">
                  {t('pipelinePage.attempts', { count: selectedStep.attempts })} ·{' '}
                  {selectedStep.started_at
                    ? new Date(selectedStep.started_at).toLocaleTimeString()
                    : '—'}
                </p>
                {Object.keys(selectedStep.output).length > 0 ? (
                  <details>
                    <summary>{t('pipelinePage.output')}</summary>
                    <pre className="json-preview">
                      {JSON.stringify(selectedStep.output, null, 2)}
                    </pre>
                  </details>
                ) : null}
              </>
            ) : null}
          </section>

          {selection ? (
            <section className="card" aria-label={t('pipelinePage.selectionCard')}>
              <h2>{t('pipelinePage.selectionCard')}</h2>
              <p>
                <strong>{selection.selected.name.zh}</strong> ·{' '}
                {selection.selected.score.toFixed(3)}
              </p>
              <p className="muted">
                {t('pipelinePage.model')}: {selection.model ?? t('pipelinePage.ruleFallback')} ·{' '}
                {t('pipelinePage.provider')}:{' '}
                {selection.provider_name ?? t('pipelinePage.ruleFallback')}
              </p>
              <p className="muted">
                {t('pipelinePage.tokens')}: {selection.usage.input_tokens} /{' '}
                {selection.usage.output_tokens} · {t('pipelinePage.cost')}:{' '}
                {selection.usage.estimated_cost.toFixed(6)} {selection.usage.currency}
              </p>
              {selection.degraded ? (
                <p className="notice">
                  {t('pipelinePage.degraded')}: {selection.degradation_reason ?? '—'}
                </p>
              ) : null}
              {selection.needs_confirmation ? (
                <p className="notice">{t('pipelinePage.needsConfirmation')}</p>
              ) : null}
              <button className="btn" type="button" onClick={() => void openTop3()}>
                {t('pipelinePage.top3')}
              </button>
              <div className="inline-form pipeline-correction">
                <input
                  className="input"
                  aria-label={t('pipelinePage.correction')}
                  placeholder={t('pipelinePage.correctionPlaceholder')}
                  value={correction}
                  onChange={(event) => setCorrection(event.target.value)}
                />
                <button
                  className="btn"
                  type="button"
                  onClick={() => void applyCorrection()}
                  disabled={correcting || !correction.trim()}
                >
                  {correcting
                    ? t('pipelinePage.applyingCorrection')
                    : t('pipelinePage.applyCorrection')}
                </button>
              </div>
              <div data-testid="pipeline-figure">
                <ChartFigure selectionId={selection.id} />
              </div>
            </section>
          ) : (
            <section className="card">
              <p className="muted">{t('pipelinePage.noSelection')}</p>
            </section>
          )}
        </aside>
      </div>

      {top3Open && selection ? (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setTop3Open(false)
          }}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={t('pipelinePage.top3')}
          >
            <h2>{t('pipelinePage.top3')}</h2>
            <p className="muted">{t('pipelinePage.top3Hint')}</p>
            <ol className="top3-list" data-testid="pipeline-top3">
              {selection.top3.map((entry) => (
                <li key={entry.chart_id} className={entry.selected ? 'selected' : ''}>
                  <div>
                    <strong>{entry.name.zh}</strong>
                    <span className="muted"> · {entry.score.toFixed(3)}</span>
                    {entry.selected ? (
                      <span className="status-pill status-succeeded">
                        {t('pipelinePage.currentChart')}
                      </span>
                    ) : null}
                    <p className="muted">{entry.reason}</p>
                  </div>
                  {!entry.selected ? (
                    <button
                      className="btn"
                      type="button"
                      onClick={() => void chooseChart(entry.chart_id)}
                      disabled={busy}
                    >
                      {t('pipelinePage.useThisChart')}
                    </button>
                  ) : null}
                </li>
              ))}
            </ol>
            <div className="modal-actions">
              <button className="btn" type="button" onClick={() => setTop3Open(false)}>
                {t('common.close')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
