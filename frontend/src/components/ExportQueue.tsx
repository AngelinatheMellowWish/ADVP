import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  listExportJobs,
  retryExportJob,
  type ExportJob,
} from '../api/exportJobs'
import { errorMessage } from '../api/projects'

type ExportQueueProps = {
  projectId?: string
  runId: string
  refreshKey?: number
}

export function ExportQueue({ projectId, runId, refreshKey = 0 }: ExportQueueProps) {
  const { t } = useTranslation()
  const [jobs, setJobs] = useState<ExportJob[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setJobs(await listExportJobs({ projectId, runId, limit: 100 }))
      setError(null)
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }, [projectId, runId])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  useEffect(() => {
    if (!jobs.some((job) => job.status === 'pending' || job.status === 'running')) return
    const timer = window.setInterval(() => void load(), 2000)
    return () => window.clearInterval(timer)
  }, [jobs, load])

  async function retry(jobId: string) {
    setBusy(true)
    try {
      await retryExportJob(jobId)
      await load()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card export-queue" data-testid="export-queue">
      <div className="panel-title">
        <h2>{t('reportPage.queue.title')}</h2>
        <button className="btn" type="button" onClick={() => void load()}>
          {t('reportPage.queue.refresh')}
        </button>
      </div>
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {jobs.length === 0 ? (
        <p className="muted">{t('reportPage.queue.empty')}</p>
      ) : (
        <ul className="export-job-list">
          {jobs.map((job) => (
            <li key={job.id} data-testid={`export-job-${job.id}`}>
              <span className="badge">{job.kind}</span>
              <span>{job.format.toUpperCase()}</span>
              <span className={`job-status job-status-${job.status}`}>
                {t(`reportPage.queue.statuses.${job.status}`, {
                  defaultValue: job.status,
                })}
              </span>
              {job.error ? <span className="muted">{job.error}</span> : null}
              {job.status === 'failed' ? (
                <button
                  className="btn"
                  type="button"
                  onClick={() => void retry(job.id)}
                  disabled={busy}
                >
                  {t('reportPage.queue.retry')}
                </button>
              ) : null}
              {job.status === 'succeeded' && job.download_url ? (
                <a className="btn" href={job.download_url}>
                  {t('reportPage.queue.download')}
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
