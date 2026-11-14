import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import {
  deleteSavedSqlConnection,
  errorMessage,
  forgetSavedSqlConnection,
  importSqlDataset,
  listSqlColumns,
  listSqlConnections,
  listSqlTables,
  previewSql,
  saveSqlConnection,
  testSavedSqlConnection,
  testSqlConnection,
  type SqlColumnInfo,
  type SqlPreviewResponse,
  type SqlSavedConnection,
  type SqlTableInfo,
} from '../api/projects'

export type SqlImportPanelState = 'loading' | 'empty' | 'error' | 'ready'

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function tableLabel(table: SqlTableInfo): string {
  return table.schema_name ? `${table.schema_name}.${table.name}` : table.name
}

function SqlPreviewTable({ preview }: { preview: SqlPreviewResponse }) {
  const { t } = useTranslation()
  const columns = preview.columns.map((column) => column.name)
  if (columns.length === 0) {
    return <p className="muted">{t('importPage.database.noPreviewColumns')}</p>
  }
  return (
    <div className="table-wrap">
      <table className="preview-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length}>{t('importPage.database.noPreviewRows')}</td>
            </tr>
          ) : (
            preview.rows.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td key={column}>{renderValue(row[column])}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

export function SqlImportPanel({
  projectId,
  onImported,
  onStateChange,
}: {
  projectId: string
  onImported: (datasetId: string) => void | Promise<void>
  onStateChange?: (state: SqlImportPanelState) => void
}) {
  const { t } = useTranslation()
  const [url, setUrl] = useState('')
  const [query, setQuery] = useState('SELECT * FROM ')
  const [name, setName] = useState('')
  const [tables, setTables] = useState<SqlTableInfo[]>([])
  const [columns, setColumns] = useState<SqlColumnInfo[]>([])
  const [selectedTable, setSelectedTable] = useState<string | null>(null)
  const [preview, setPreview] = useState<SqlPreviewResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [connections, setConnections] = useState<SqlSavedConnection[]>([])
  const [savedId, setSavedId] = useState('')
  const [remember, setRemember] = useState(false)
  const [connectionName, setConnectionName] = useState('')

  const state: SqlImportPanelState = busy
    ? 'loading'
    : error
      ? 'error'
      : tables.length > 0 || columns.length > 0 || preview || message
        ? 'ready'
        : 'empty'

  useEffect(() => {
    onStateChange?.(state)
  }, [onStateChange, state])

  useEffect(() => {
    let cancelled = false
    listSqlConnections()
      .then((result) => {
        if (!cancelled) setConnections(result.connections ?? [])
      })
      .catch(() => {
        if (!cancelled) setConnections([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  function selectSavedConnection(id: string) {
    setSavedId(id)
    const saved = connections.find((item) => item.id === id)
    if (saved) {
      setUrl(saved.label)
      setConnectionName(saved.name)
    }
  }

  async function refreshConnections() {
    const result = await listSqlConnections()
    setConnections(result.connections ?? [])
  }

  async function handleSaveConnection() {
    const name = connectionName.trim()
    if (!name || !url.trim()) {
      setError(t('importPage.database.savedNeedsName'))
      return
    }
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const saved = await saveSqlConnection({ name, url: url.trim() })
      await refreshConnections()
      setSavedId(saved.id)
      setRemember(true)
      setMessage(t('importPage.database.saved', { name: saved.name }))
    } catch (caught) {
      setError(`${t('importPage.database.saveFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleDeleteSaved() {
    if (!savedId) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await deleteSavedSqlConnection(savedId)
      await refreshConnections()
      setSavedId('')
      setConnectionName('')
      setMessage(t('importPage.database.deletedSaved'))
    } catch (caught) {
      setError(`${t('importPage.database.saveFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleForgetSaved() {
    if (!savedId) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const saved = await forgetSavedSqlConnection(savedId)
      await refreshConnections()
      setMessage(t('importPage.database.forgotSaved', { name: saved.name }))
    } catch (caught) {
      setError(`${t('importPage.database.saveFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleTest() {
    if (!url.trim() && !savedId) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = savedId
        ? await testSavedSqlConnection(savedId)
        : await testSqlConnection(url.trim())
      setMessage(
        t('importPage.database.testSuccess', {
          dialect: result.dialect,
          label: result.label,
        }),
      )
    } catch (caught) {
      setError(`${t('importPage.database.testFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleTables() {
    if (!url.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    setColumns([])
    setSelectedTable(null)
    setPreview(null)
    try {
      const result = await listSqlTables(url.trim())
      setTables(result.tables)
      setMessage(
        t('importPage.database.tablesFound', {
          count: result.tables.length,
          dialect: result.dialect,
        }),
      )
    } catch (caught) {
      setError(`${t('importPage.database.tablesFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleSelectTable(table: SqlTableInfo) {
    if (!url.trim()) return
    const label = tableLabel(table)
    setQuery(`SELECT * FROM ${label}`)
    setSelectedTable(label)
    setColumns([])
    setPreview(null)
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await listSqlColumns(url.trim(), label)
      setColumns(result.columns)
    } catch (caught) {
      setError(`${t('importPage.database.columnsFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handlePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!url.trim() || !query.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      setPreview(await previewSql(url.trim(), query.trim()))
    } catch (caught) {
      setError(`${t('importPage.database.previewFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleImport() {
    if (!url.trim() || !query.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const dataset = await importSqlDataset(
        projectId,
        url.trim(),
        query.trim(),
        name.trim() || undefined,
      )
      setMessage(
        t('importPage.database.importSuccess', {
          name: dataset.name,
          count: dataset.row_count,
        }),
      )
      setPreview(null)
      setColumns([])
      setSelectedTable(null)
      await onImported(dataset.id)
    } catch (caught) {
      setError(`${t('importPage.database.importFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel sql-import-panel" data-testid="sql-import-panel">
      <h3>{t('importPage.database.title')}</h3>
      <p className="muted">{t('importPage.database.description')}</p>
      <p className="muted">{t('importPage.database.readOnlyHint')}</p>
      <div className="stack-form">
        {connections.length > 0 ? (
          <>
            <label htmlFor="sql-saved">{t('importPage.database.savedSelect')}</label>
            <select
              id="sql-saved"
              className="input"
              value={savedId}
              onChange={(event) => selectSavedConnection(event.target.value)}
              disabled={busy}
            >
              <option value="">{t('importPage.database.savedNone')}</option>
              {connections.map((connection) => (
                <option key={connection.id} value={connection.id}>
                  {connection.name} ({connection.dialect})
                </option>
              ))}
            </select>
          </>
        ) : null}
        <label className="checkbox-row" htmlFor="sql-remember">
          <span>{t('importPage.database.remember')}</span>
          <input
            id="sql-remember"
            type="checkbox"
            checked={remember}
            onChange={(event) => setRemember(event.target.checked)}
            disabled={busy}
          />
        </label>
        {remember ? (
          <div className="inline-form">
            <input
              aria-label={t('importPage.database.connectionName')}
              className="input"
              placeholder={t('importPage.database.connectionNamePlaceholder')}
              value={connectionName}
              onChange={(event) => setConnectionName(event.target.value)}
            />
            <button
              className="button"
              type="button"
              onClick={() => void handleSaveConnection()}
              disabled={busy || !url.trim() || !connectionName.trim()}
            >
              {t('importPage.database.saveConnection')}
            </button>
          </div>
        ) : null}
        {savedId ? (
          <div className="inline-form">
            <button
              className="button"
              type="button"
              onClick={() => void handleForgetSaved()}
              disabled={busy}
            >
              {t('importPage.database.forgetSaved')}
            </button>
            <button
              className="button"
              type="button"
              onClick={() => void handleDeleteSaved()}
              disabled={busy}
            >
              {t('importPage.database.deleteSaved')}
            </button>
          </div>
        ) : null}
        <p className="hint">{t('importPage.database.savedHint')}</p>
        <label htmlFor="sql-url">{t('importPage.database.urlLabel')}</label>
        <input
          id="sql-url"
          className="input"
          placeholder={t('importPage.database.urlPlaceholder')}
          value={url}
          onChange={(event) => setUrl(event.target.value)}
        />
        <div className="inline-form">
          <button
            className="button"
            type="button"
            onClick={() => void handleTest()}
            disabled={busy}
          >
            {t('importPage.database.test')}
          </button>
          <button
            className="button"
            type="button"
            onClick={() => void handleTables()}
            disabled={busy}
          >
            {t('importPage.database.browse')}
          </button>
        </div>
        {tables.length > 0 ? (
          <section>
            <h4>{t('importPage.database.tablesTitle')}</h4>
            <ul className="dataset-list">
              {tables.map((table) => (
                <li key={`${table.type}-${table.name}`}>
                  <button
                    className={`list-button ${
                      selectedTable === tableLabel(table) ? 'active' : ''
                    }`}
                    type="button"
                    onClick={() => void handleSelectTable(table)}
                    disabled={busy}
                  >
                    <span>{table.name}</span>
                    <span className="muted">{table.type}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {selectedTable ? (
          <section>
            <h4>{t('importPage.database.columnsTitle', { table: selectedTable })}</h4>
            {columns.length === 0 && !busy ? (
              <p className="muted">{t('importPage.database.noColumns')}</p>
            ) : (
              <div className="table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>
                      <th>{t('importPage.database.columnName')}</th>
                      <th>{t('importPage.database.columnType')}</th>
                      <th>{t('importPage.database.columnNullable')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {columns.map((column) => (
                      <tr key={column.name} data-testid={`sql-column-${column.name}`}>
                        <td>{column.name}</td>
                        <td>{column.type}</td>
                        <td>
                          {column.nullable
                            ? t('importPage.database.yes')
                            : t('importPage.database.no')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ) : null}
        <form onSubmit={handlePreview} className="stack-form">
          <label htmlFor="sql-query">{t('importPage.database.queryLabel')}</label>
          <textarea
            id="sql-query"
            rows={5}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <label htmlFor="sql-name">{t('importPage.database.nameLabel')}</label>
          <input
            id="sql-name"
            className="input"
            placeholder={t('importPage.database.namePlaceholder')}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <div className="inline-form">
            <button className="button" type="submit" disabled={busy || !query.trim()}>
              {t('importPage.database.preview')}
            </button>
            <button
              className="button"
              type="button"
              onClick={() => void handleImport()}
              disabled={busy || !query.trim()}
            >
              {busy
                ? t('importPage.database.importing')
                : t('importPage.database.import')}
            </button>
          </div>
        </form>
      </div>
      {message ? <p className="muted">{message}</p> : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {preview ? (
        <>
          <div className="metrics">
            <span className="metric">
              {t('importPage.database.dialect')} <strong>{preview.dialect}</strong>
            </span>
            <span className="metric">
              {t('importPage.database.returned')} <strong>{preview.rows.length}</strong>
            </span>
            <span className="metric">
              {t('importPage.database.truncated')}{' '}
              <strong>
                {preview.truncated
                  ? t('importPage.database.yes')
                  : t('importPage.database.no')}
              </strong>
            </span>
          </div>
          <SqlPreviewTable preview={preview} />
        </>
      ) : null}
    </section>
  )
}
