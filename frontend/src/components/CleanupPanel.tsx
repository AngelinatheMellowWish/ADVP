import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorMessage, formatBytes } from '../api/projects'
import {
  previewCleanup,
  runCleanup,
  type CleanupPreview,
  type CleanupResult,
} from '../api/system'

const CATEGORIES = ['imports', 'derived', 'logs', 'search_index', 'cache'] as const

export function CleanupPanel() {
  const { t } = useTranslation()
  const [preview, setPreview] = useState<CleanupPreview | null>(null)
  const [selected, setSelected] = useState<string[]>([...CATEGORIES])
  const [allowReferenced, setAllowReferenced] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<CleanupResult | null>(null)

  useEffect(() => {
    let cancelled = false
    setBusy(true)
    setError(null)
    previewCleanup(selected, allowReferenced)
      .then((value) => {
        if (!cancelled) {
          setPreview(value)
          setResult(null)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
      .finally(() => {
        if (!cancelled) setBusy(false)
      })
    return () => {
      cancelled = true
    }
  }, [selected, allowReferenced])

  function toggle(key: string) {
    setSelected((current) =>
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key],
    )
  }

  async function execute() {
    setBusy(true)
    setError(null)
    try {
      const outcome = await runCleanup(selected, allowReferenced)
      setResult(outcome)
      setConfirming(false)
      setPreview(await previewCleanup(selected, allowReferenced))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack-form" data-testid="cleanup-panel">
      <p className="muted">{t('settingsPage.cleanup.hint')}</p>
      {preview?.categories?.map((category) => (
        <label
          key={category.key}
          className="checkbox-row"
          data-testid={`cleanup-category-${category.key}`}
        >
          <span>
            <input
              type="checkbox"
              checked={selected.includes(category.key)}
              disabled={busy}
              onChange={() => toggle(category.key)}
            />
            {t(`settingsPage.cleanup.categories.${category.key}`)}
          </span>
          <span className="muted">
            {t('settingsPage.cleanup.deletable', {
              size: formatBytes(category.deletable_bytes),
              files: category.deletable_files,
            })}
            {category.protected_files > 0
              ? ` · ${t('settingsPage.cleanup.protected', {
                  size: formatBytes(category.protected_bytes),
                  files: category.protected_files,
                })}`
              : ''}
          </span>
        </label>
      ))}
      <div className="button-row">
        <button
          className="btn"
          type="button"
          disabled={busy || selected.length === 0}
          onClick={() => setConfirming(true)}
          data-testid="cleanup-execute"
        >
          {t('settingsPage.cleanup.execute')}
        </button>
        {preview ? (
          <span className="muted" data-testid="cleanup-total">
            {t('settingsPage.cleanup.total', {
              size: formatBytes(preview.totals.deletable_bytes),
            })}
          </span>
        ) : null}
      </div>
      {confirming ? (
        <div className="card" data-testid="cleanup-confirm">
          <p className="error-text">{t('settingsPage.cleanup.confirmWarning')}</p>
          {selected.includes('imports') ? (
            <label className="checkbox-row">
              <span>{t('settingsPage.cleanup.allowReferenced')}</span>
              <input
                type="checkbox"
                checked={allowReferenced}
                onChange={(event) => setAllowReferenced(event.target.checked)}
              />
            </label>
          ) : null}
          <div className="button-row">
            <button
              className="btn home-primary"
              type="button"
              disabled={busy}
              onClick={() => void execute()}
              data-testid="cleanup-confirm-button"
            >
              {t('settingsPage.cleanup.confirm')}
            </button>
            <button className="btn" type="button" onClick={() => setConfirming(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      ) : null}
      {result ? (
        <p className="notice" data-testid="cleanup-result">
          {t('settingsPage.cleanup.done', {
            size: formatBytes(result.totals.deleted_bytes),
            files: result.totals.deleted_files,
          })}
        </p>
      ) : null}
      {error ? <p className="error-text">{error}</p> : null}
    </div>
  )
}
