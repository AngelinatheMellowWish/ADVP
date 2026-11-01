import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { getPipelineRun, type PipelineRun } from '../api/pipelines'
import { errorMessage } from '../api/projects'
import { TracePanel } from '../components/TracePanel'

export function P09Trace() {
  const { t } = useTranslation()
  const { projectId } = useParams<{ projectId?: string }>()
  const [params] = useSearchParams()
  const runId = params.get('run')
  const [run, setRun] = useState<PipelineRun | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!runId) {
      setRun(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    getPipelineRun(runId)
      .then((payload) => {
        if (!cancelled) setRun(payload)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [runId])

  return (
    <section className="page" data-testid="page-p09">
      <header className="import-head">
        <div>
          <h1>{t('tracePage.title')}</h1>
          <p className="muted">
            {runId ? `${t('tracePage.run')} ${runId}` : t('tracePage.hint')}
          </p>
        </div>
        {projectId ? (
          <Link className="btn" to={`/projects/${projectId}/pipeline`}>
            {t('tracePage.backToPipeline')}
          </Link>
        ) : null}
      </header>
      {error ? <p className="error-text">{error}</p> : null}
      {loading ? <p className="muted">{t('tracePage.loading')}</p> : null}
      {!runId ? <p className="muted">{t('tracePage.missingRun')}</p> : null}
      {run ? <TracePanel run={run} onRunChanged={setRun} /> : null}
    </section>
  )
}
