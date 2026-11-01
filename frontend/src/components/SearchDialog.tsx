import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { errorMessage } from '../api/projects'
import { searchAll, type SearchResponse } from '../api/search'

export function SearchDialog({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setResult(null)
      setError(null)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const term = query.trim()
    if (!term) return
    setBusy(true)
    setError(null)
    try {
      setResult(await searchAll(term))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  function openHit(url: string) {
    navigate(url)
    onClose()
  }

  if (!open) return null

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="modal search-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('search.title')}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="panel-title">
          <h2>{t('search.title')}</h2>
          <button className="btn" type="button" onClick={onClose}>
            {t('common.close')}
          </button>
        </div>
        <form className="inline-form" onSubmit={(event) => void submit(event)}>
          <input
            className="input"
            autoFocus
            value={query}
            placeholder={t('search.placeholder')}
            aria-label={t('search.placeholder')}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button className="btn home-primary" type="submit" disabled={busy}>
            {busy ? t('search.searching') : t('search.action')}
          </button>
        </form>
        {error ? <p className="error-text">{error}</p> : null}
        {result && result.total === 0 ? <p className="muted">{t('search.noResults')}</p> : null}
        {result
          ? Object.entries(result.groups).map(([kind, hits]) =>
              hits.length > 0 ? (
                <section key={kind} className="search-group">
                  <h3>{t(`search.kinds.${kind}`, { defaultValue: kind })}</h3>
                  <ul>
                    {hits.map((hit) => (
                      <li key={`${hit.kind}-${hit.object_id}`}>
                        <button className="list-button" onClick={() => openHit(hit.url)}>
                          <span>{hit.title}</span>
                          <span className="muted">{hit.snippet}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null,
            )
          : null}
      </section>
    </div>
  )
}
