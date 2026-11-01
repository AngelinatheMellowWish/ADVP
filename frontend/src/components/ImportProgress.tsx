import { useTranslation } from 'react-i18next'

import type { ImportJobDetail } from '../api/importJobs'

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled'])

type ImportProgressProps = {
  job: ImportJobDetail
  onCancel: () => void
  onRetry: () => void
}

export function ImportProgress({ job, onCancel, onRetry }: ImportProgressProps) {
  const { t } = useTranslation()
  const percent = Math.round(Math.min(1, Math.max(0, job.progress)) * 100)
  const stageLabel = t(`importPage.progress.stage.${job.stage}`, {
    defaultValue: job.stage,
  })
  const finished = TERMINAL.has(job.status)

  return (
    <section className="card import-progress" aria-live="polite">
      <h2>{t('importPage.progress.title')}</h2>
      <div className="progress-track">
        <div
          className="progress-fill"
          role="progressbar"
          aria-label={stageLabel}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          style={{ width: `${percent}%` }}
        />
      </div>
      <p>
        <strong>{stageLabel}</strong> {t('importPage.progress.percent', { value: percent })}
      </p>
      {job.message ? <p className="muted import-progress-message">{job.message}</p> : null}
      {job.error ? (
        <p className="error-text" role="alert">
          {t('importPage.progress.failed', { message: job.error })}
        </p>
      ) : null}
      <div className="import-progress-actions">
        {!finished ? (
          <button
            className="btn"
            type="button"
            onClick={onCancel}
            disabled={job.cancel_requested}
          >
            {job.cancel_requested
              ? t('importPage.progress.cancelRequested')
              : t('importPage.progress.cancel')}
          </button>
        ) : job.status === 'failed' || job.status === 'cancelled' ? (
          <button className="btn" type="button" onClick={onRetry}>
            {t('importPage.progress.retry')}
          </button>
        ) : (
          <span className="muted">{t('importPage.progress.done')}</span>
        )}
      </div>
    </section>
  )
}
