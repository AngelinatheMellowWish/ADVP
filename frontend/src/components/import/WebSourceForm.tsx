import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import {
  ApiError,
  errorMessage,
  importWeb,
  inspectWeb,
  type WebTablesResponse,
} from '../../api/projects'
import { isValidHttpUrl } from './remoteSourceConfig'

export type WebSourceState = 'loading' | 'empty' | 'error' | 'ready'

type BusyState = 'inspect' | 'import' | null

export function WebSourceForm({
  projectId,
  onImported,
  onStateChange,
}: {
  projectId: string
  onImported: (datasetId: string) => void | Promise<void>
  onStateChange?: (state: WebSourceState) => void
}) {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [inspectedUrl, setInspectedUrl] = useState('')
  const [name, setName] = useState('')
  const [result, setResult] = useState<WebTablesResponse | null>(null)
  const [selected, setSelected] = useState(-1)
  const [busy, setBusy] = useState<BusyState>(null)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const state: WebSourceState = busy
    ? 'loading'
    : error
      ? 'error'
      : result
        ? 'ready'
        : 'empty'

  useEffect(() => {
    onStateChange?.(state)
  }, [onStateChange, state])

  const selectedTable = result
    ? result.tables.find((table) => table.index === selected) ?? result.tables[0]
    : null
  const urlInvalid = submitted && !isValidHttpUrl(url)

  async function handleInspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitted(true)
    setError(null)
    setResult(null)
    setSelected(-1)
    if (!isValidHttpUrl(url)) {
      setError(t('importPage.web.invalidUrl'))
      return
    }
    setBusy('inspect')
    try {
      const response = await inspectWeb(projectId, url.trim())
      setResult(response)
      setInspectedUrl(url.trim())
      setSelected(response.tables.length > 0 ? response.tables[0].index : -1)
    } catch (caught) {
      if (caught instanceof ApiError && caught.code === 'web_url_blocked') {
        setError(t('importPage.web.blocked'))
      } else {
        setError(`${t('importPage.web.inspectFailed')} ${errorMessage(caught)}`)
      }
    } finally {
      setBusy(null)
    }
  }

  async function handleImport() {
    if (!result || !selectedTable || !inspectedUrl) return
    setBusy('import')
    setError(null)
    try {
      const dataset = await importWeb(
        projectId,
        inspectedUrl,
        selectedTable.index,
        name.trim() || undefined,
      )
      await onImported(dataset.id)
    } catch (caught) {
      setError(`${t('importPage.web.importFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="panel remote-source-panel" data-testid="web-source-form">
      <h3>{t('importPage.web.title')}</h3>
      <p className="muted">{t('importPage.web.description')}</p>

      <form className="stack-form" onSubmit={handleInspect}>
        <label htmlFor="web-url">{t('importPage.web.urlLabel')}</label>
        <input
          id="web-url"
          className="input"
          placeholder={t('importPage.web.urlPlaceholder')}
          value={url}
          aria-invalid={urlInvalid}
          onChange={(event) => setUrl(event.target.value)}
        />
        <p className={urlInvalid ? 'hint error-text' : 'hint'}>
          {t('importPage.web.urlHint')}
        </p>

        <div className="import-actions">
          <button className="btn" type="submit" disabled={busy !== null}>
            {busy === 'inspect'
              ? t('importPage.web.inspecting')
              : t('importPage.web.inspect')}
          </button>
        </div>
      </form>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}

      {result && selectedTable ? (
        <div className="import-web-result">
          <section>
            <h4>{t('importPage.web.tablesTitle')}</h4>
            <p className="hint">
              <span className={`source-badge source-badge-${result.source}`}>
                {t(`importPage.web.sources.${result.source}`)}
              </span>
              {' · '}
              <span>{t('importPage.web.elapsed', { ms: result.elapsed_ms })}</span>
            </p>
            {result.warning ? <p className="hint">{result.warning}</p> : null}
            {result.tables.length > 0 ? (
              <ul className="file-list">
                {result.tables.map((table) => (
                  <li key={table.index}>
                    <button
                      className="btn"
                      type="button"
                      aria-pressed={selectedTable.index === table.index}
                      onClick={() => setSelected(table.index)}
                    >
                      {t('importPage.web.tableOption', {
                        index: table.index + 1,
                        rows: table.row_count,
                        columns: table.column_count,
                      })}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">{t('importPage.web.noTables')}</p>
            )}
          </section>

          <section>
            <h4>{t('importPage.web.previewTitle')}</h4>
            <div className="table-wrap">
              <table className="preview-table">
                <thead>
                  <tr>
                    {selectedTable.headers.map((header) => (
                      <th key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {selectedTable.preview.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {selectedTable.headers.map((header, columnIndex) => (
                        <td key={header}>{String(row[columnIndex] ?? '')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <label htmlFor="web-name">{t('importPage.web.nameLabel')}</label>
          <input
            id="web-name"
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />

          <div className="import-actions">
            <button
              className="btn home-primary"
              type="button"
              onClick={handleImport}
              disabled={busy !== null}
            >
              {busy === 'import'
                ? t('importPage.web.importing')
                : t('importPage.web.import')}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
