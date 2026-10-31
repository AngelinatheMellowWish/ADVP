import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cleanDataset, type CleanStep } from '../api/cleaning'
import { errorMessage, type DatasetDetail, type ProfileIssue } from '../api/projects'
import {
  applyQualitySuggestion,
  ignoreQualityIssue,
  type QualityApplyResponse,
} from '../api/quality'

const ACTIONABLE = new Set([
  'duplicate_rows',
  'missing_values',
  'numeric_outliers',
  'type_conflict',
])

type QualityPanelProps = {
  dataset: DatasetDetail
  onChanged: () => void
}

export function QualityPanel({ dataset, onChanged }: QualityPanelProps) {
  const { t } = useTranslation()
  const [preview, setPreview] = useState<QualityApplyResponse | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ignored = new Set(dataset.ignored_issues ?? [])
  const issues = (dataset.profile.issues ?? []).filter((issue) => !ignored.has(issue.code))

  async function handleApply(issue: ProfileIssue) {
    setBusy(`apply-${issue.code}`)
    setError(null)
    try {
      setPreview(
        await applyQualitySuggestion(dataset.id, issue.code, issue.column ?? null),
      )
    } catch (caught) {
      setError(`${t('quality.failed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(null)
    }
  }

  async function handleIgnore(issue: ProfileIssue) {
    setBusy(`ignore-${issue.code}`)
    setError(null)
    try {
      await ignoreQualityIssue(dataset.id, issue.code)
      onChanged()
    } catch (caught) {
      setError(`${t('quality.failed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(null)
    }
  }

  async function confirmApply() {
    if (!preview) return
    setApplying(true)
    setError(null)
    try {
      await cleanDataset(dataset.id, preview.steps as CleanStep[], { dryRun: false })
      setPreview(null)
      onChanged()
    } catch (caught) {
      setError(`${t('quality.failed')} ${errorMessage(caught)}`)
    } finally {
      setApplying(false)
    }
  }

  return (
    <section className="card quality-panel" aria-labelledby="quality-title">
      <div className="home-section-head">
        <h2 id="quality-title">{t('quality.title')}</h2>
        <span className="muted">
          {t('quality.score', { score: dataset.quality_score })}
        </span>
      </div>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}

      {issues.length === 0 ? (
        <p className="muted">{t('quality.empty')}</p>
      ) : (
        <ul className="quality-list">
          {issues.map((issue) => (
            <li key={`${issue.code}-${issue.column ?? ''}`} className="quality-issue">
              <div className="quality-issue-head">
                <span className={`quality-badge quality-${issue.severity}`}>
                  {t(`quality.severity.${issue.severity}`, {
                    defaultValue: issue.severity,
                  })}
                </span>
                <strong>{issue.message}</strong>
              </div>
              {issue.column ? (
                <p className="muted">{t('quality.column', { column: issue.column })}</p>
              ) : null}
              {issue.suggestion ? <p className="muted">{issue.suggestion}</p> : null}
              {typeof issue.affected_rows === 'number' ? (
                <p className="muted">
                  {t('quality.affected', { count: issue.affected_rows })}
                </p>
              ) : null}
              <div className="quality-issue-actions">
                {ACTIONABLE.has(issue.code) ? (
                  <button
                    className="btn"
                    type="button"
                    aria-label={`${t('quality.apply')} ${issue.code}`}
                    onClick={() => handleApply(issue)}
                    disabled={busy === `apply-${issue.code}`}
                  >
                    {t('quality.apply')}
                  </button>
                ) : (
                  <span className="muted">{t('quality.noSuggestion')}</span>
                )}
                <button
                  className="btn"
                  type="button"
                  aria-label={`${t('quality.ignore')} ${issue.code}`}
                  onClick={() => handleIgnore(issue)}
                  disabled={busy === `ignore-${issue.code}`}
                >
                  {t('quality.ignore')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {preview ? (
        <div className="modal-backdrop">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={t('quality.previewTitle')}
          >
            <h2>{t('quality.previewTitle')}</h2>
            <p>
              {t('quality.previewSummary', {
                before: preview.before_rows,
                after: preview.after_rows,
                affected: preview.affected_rows,
              })}
            </p>
            <ul className="quality-steps">
              {preview.steps.map((step, index) => (
                <li key={index}>
                  {step.operation}
                  {step.column ? ` · ${step.column}` : ''}
                </li>
              ))}
            </ul>
            <div className="table-wrap">
              <table className="preview-table">
                <tbody>
                  {preview.preview.slice(0, 5).map((row, index) => (
                    <tr key={index}>
                      {Object.values(row).map((value, cell) => (
                        <td key={cell}>{String(value ?? '')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="modal-actions">
              <button
                className="btn"
                type="button"
                onClick={() => setPreview(null)}
                disabled={applying}
              >
                {t('common.cancel')}
              </button>
              <button
                className="btn home-primary"
                type="button"
                onClick={confirmApply}
                disabled={applying}
              >
                {applying ? t('quality.applying') : t('quality.confirm')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
