import { useEffect, useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'

import {
  cancelImportJob,
  createImportJob,
  getImportJob,
  pickFile,
  retryImportJob,
  uploadFile,
  type ImportJobDetail,
  type ImportJobStatus,
} from '../api/importJobs'
import {
  errorMessage,
  importDocument,
  importTextStats,
  inspectDataset,
  inspectDocument,
  type DocumentTablesResponse,
  type InspectResponse,
} from '../api/projects'
import { ImportProgress } from '../components/ImportProgress'
import { MultiFileDialog } from '../components/MultiFileDialog'

const SOURCE_TABS = ['file', 'database', 'remote', 'document', 'web', 'live'] as const
type SourceTab = (typeof SOURCE_TABS)[number]

const TERMINAL: ImportJobStatus[] = ['succeeded', 'failed', 'cancelled']

export function P02Import() {
  const { t } = useTranslation()
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [tab, setTab] = useState<SourceTab>('file')
  const [paths, setPaths] = useState<string[]>([])
  const [manualPath, setManualPath] = useState('')
  const [mode, setMode] = useState<'independent' | 'union' | 'join'>('independent')
  const [datasetName, setDatasetName] = useState('')
  const [inspected, setInspected] = useState<InspectResponse | null>(null)
  const [inspecting, setInspecting] = useState(false)
  const [starting, setStarting] = useState(false)
  const [activeJob, setActiveJob] = useState<ImportJobDetail | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copyOpen, setCopyOpen] = useState(false)
  const [copyFiles, setCopyFiles] = useState<File[]>([])
  const [copying, setCopying] = useState(false)
  const [multiOpen, setMultiOpen] = useState(false)
  const [docPath, setDocPath] = useState('')
  const [docName, setDocName] = useState('')
  const [docResult, setDocResult] = useState<DocumentTablesResponse | null>(null)
  const [docBusy, setDocBusy] = useState<string | null>(null)
  const [docError, setDocError] = useState<string | null>(null)

  useEffect(() => {
    if (!activeJob || TERMINAL.includes(activeJob.status)) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      getImportJob(activeJob.id)
        .then((job) => {
          if (cancelled) return
          if (job.status === 'succeeded' && job.result_dataset_id && projectId) {
            navigate(`/projects/${projectId}/data?dataset=${job.result_dataset_id}`)
            return
          }
          setActiveJob(job)
        })
        .catch((caught: unknown) => {
          if (!cancelled) setError(errorMessage(caught))
        })
    }, 400)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [activeJob, navigate, projectId])

  function addPath(raw: string) {
    const value = raw.trim()
    if (!value) return
    setPaths((current) => (current.includes(value) ? current : [...current, value]))
    setNotice(null)
  }

  function addManualPath() {
    addPath(manualPath)
    setManualPath('')
  }

  async function browseFile() {
    setError(null)
    try {
      const result = await pickFile()
      if (result.path) addPath(result.path)
    } catch (caught) {
      setError(`${t('importPage.file.inspectFailed')} ${errorMessage(caught)}`)
    }
  }

  async function inspectSelected() {
    if (!projectId || paths.length === 0) {
      setError(t('importPage.file.emptyPaths'))
      return
    }
    setInspecting(true)
    setError(null)
    setInspected(null)
    try {
      setInspected(await inspectDataset(projectId, paths[0]))
    } catch (caught) {
      setError(`${t('importPage.file.inspectFailed')} ${errorMessage(caught)}`)
    } finally {
      setInspecting(false)
    }
  }

  async function startImport() {
    if (!projectId) return
    setError(null)
    setNotice(null)
    if (paths.length === 0) {
      setError(t('importPage.file.emptyPaths'))
      return
    }
    if (mode !== 'independent') {
      if (paths.length < 2) {
        setError(t('importPage.file.multiFileNeedsTwo'))
        return
      }
      setMultiOpen(true)
      return
    }
    setStarting(true)
    setInspected(null)
    try {
      const jobs: ImportJobDetail[] = []
      for (const path of paths) {
        jobs.push(
          await createImportJob(
            projectId,
            path,
            paths.length === 1 ? datasetName.trim() || undefined : undefined,
          ),
        )
      }
      setActiveJob(jobs[0])
      if (jobs.length > 1) {
        setNotice(t('importPage.file.queuedOthers', { count: jobs.length - 1 }))
      }
    } catch (caught) {
      setError(`${t('importPage.file.importFailed')} ${errorMessage(caught)}`)
    } finally {
      setStarting(false)
    }
  }

  async function cancelJob() {
    if (!activeJob) return
    try {
      setActiveJob(await cancelImportJob(activeJob.id))
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  async function retryJob() {
    if (!activeJob) return
    try {
      setActiveJob(await retryImportJob(activeJob.id))
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    const files = Array.from(event.dataTransfer.files)
    if (files.length === 0) return
    setCopyFiles(files)
    setCopyOpen(true)
  }

  async function copySelected() {
    if (!projectId || copyFiles.length === 0) return
    setCopying(true)
    setError(null)
    try {
      const copies: Awaited<ReturnType<typeof uploadFile>>[] = []
      for (const file of copyFiles) {
        copies.push(await uploadFile(projectId, file))
      }
      setPaths((current) => [...current, ...copies.map((copy) => copy.path)])
      setCopyFiles([])
      setCopyOpen(false)
      setNotice(t('importPage.file.copyDone', { count: copies.length }))
    } catch (caught) {
      setError(`${t('importPage.file.copyFailed')} ${errorMessage(caught)}`)
    } finally {
      setCopying(false)
    }
  }

  function handleImported(datasetId: string) {
    setMultiOpen(false)
    if (projectId) {
      navigate(`/projects/${projectId}/data?dataset=${datasetId}`)
    }
  }

  async function inspectDocumentFile() {
    if (!projectId || !docPath.trim()) {
      setDocError(t('importPage.document.needsPath'))
      return
    }
    setDocBusy('inspect')
    setDocError(null)
    setDocResult(null)
    try {
      setDocResult(await inspectDocument(projectId, docPath.trim()))
    } catch (caught) {
      setDocError(`${t('importPage.document.failed')} ${errorMessage(caught)}`)
    } finally {
      setDocBusy(null)
    }
  }

  async function importDocumentTable(tableIndex: number) {
    if (!projectId) return
    setDocBusy(`table-${tableIndex}`)
    setDocError(null)
    try {
      const dataset = await importDocument(
        projectId,
        docPath.trim(),
        tableIndex,
        docName.trim() || undefined,
      )
      navigate(`/projects/${projectId}/data?dataset=${dataset.id}`)
    } catch (caught) {
      setDocError(`${t('importPage.document.failed')} ${errorMessage(caught)}`)
    } finally {
      setDocBusy(null)
    }
  }

  async function importDocumentText(shape: 'long' | 'wide') {
    if (!projectId || !docResult?.text || !docPath.trim()) return
    const facts = docResult.text.long.facts.filter((fact) => fact.include !== false)
    if (facts.length === 0) return
    setDocBusy(`text-${shape}`)
    setDocError(null)
    try {
      const dataset = await importTextStats(
        projectId,
        docPath.trim(),
        docResult.source_sha256,
        shape,
        facts,
        docName.trim() || undefined,
      )
      navigate(`/projects/${projectId}/data?dataset=${dataset.id}`)
    } catch (caught) {
      setDocError(`${t('importPage.document.failed')} ${errorMessage(caught)}`)
    } finally {
      setDocBusy(null)
    }
  }

  return (
    <section className="import-page" data-testid="page-p02">
      <header className="import-head">
        <h1>{t('importPage.title')}</h1>
        <p className="muted">{t('importPage.subtitle')}</p>
      </header>

      <div className="tab-row" role="tablist" aria-label={t('importPage.title')}>
        {SOURCE_TABS.map((source) => (
          <button
            key={source}
            className="tab"
            type="button"
            role="tab"
            aria-selected={tab === source}
            onClick={() => setTab(source)}
          >
            {t(`importPage.sources.${source}`)}
          </button>
        ))}
      </div>

      {tab === 'document' ? (
        <section className="card import-doc-card">
          <h2>{t('importPage.document.title')}</h2>

          <label htmlFor="doc-path">{t('importPage.document.pathLabel')}</label>
          <input
            id="doc-path"
            className="input"
            value={docPath}
            onChange={(event) => setDocPath(event.target.value)}
          />
          <label htmlFor="doc-name">{t('importPage.document.nameLabel')}</label>
          <input
            id="doc-name"
            className="input"
            value={docName}
            onChange={(event) => setDocName(event.target.value)}
          />
          <div className="import-actions">
            <button
              className="btn"
              type="button"
              onClick={inspectDocumentFile}
              disabled={docBusy === 'inspect'}
            >
              {docBusy === 'inspect'
                ? t('importPage.document.inspecting')
                : t('importPage.document.inspect')}
            </button>
          </div>

          {docError ? (
            <p className="error-text" role="alert">
              {docError}
            </p>
          ) : null}

          {docResult ? (
            <div className="import-doc-result">
              {docResult.tables.length > 0 ? (
                <section>
                  <h3>{t('importPage.document.tablesTitle')}</h3>
                  <ul className="file-list">
                    {docResult.tables.map((table) => (
                      <li key={table.index}>
                        <span>
                          {t('importPage.document.tableInfo', {
                            rows: table.row_count,
                            columns: table.column_count,
                          })}
                        </span>
                        <button
                          className="btn"
                          type="button"
                          aria-label={`${t('importPage.document.importTable')} ${table.index}`}
                          onClick={() => importDocumentTable(table.index)}
                          disabled={docBusy === `table-${table.index}`}
                        >
                          {t('importPage.document.importTable')}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {docResult.text ? (
                <section>
                  <h3>{t('importPage.document.textTitle')}</h3>
                  <p className="muted">
                    {t('importPage.document.longFacts', {
                      count: docResult.text.long.facts.length,
                    })}
                  </p>
                  <p className="muted">
                    {t('importPage.document.wideRows', {
                      count: docResult.text.wide.rows.length,
                    })}
                  </p>
                  <div className="import-actions">
                    <button
                      className="btn home-primary"
                      type="button"
                      onClick={() => importDocumentText('long')}
                      disabled={docBusy === 'text-long'}
                    >
                      {t('importPage.document.importLong')}
                    </button>
                    <button
                      className="btn"
                      type="button"
                      onClick={() => importDocumentText('wide')}
                      disabled={docBusy === 'text-wide'}
                    >
                      {t('importPage.document.importWide')}
                    </button>
                  </div>
                </section>
              ) : (
                <p className="muted">{t('importPage.document.noText')}</p>
              )}
            </div>
          ) : null}
        </section>
      ) : tab !== 'file' ? (
        <section className="card">
          <h2>{t('importPage.otherSources.title', { source: t(`importPage.sources.${tab}`) })}</h2>
          <p className="muted">{t('importPage.otherSources.pending')}</p>
        </section>
      ) : (
        <div className="import-layout">
          <section className="card import-file-card">
            <h2>{t('importPage.file.title')}</h2>

            <label htmlFor="import-path">{t('importPage.file.pathLabel')}</label>
            <div className="import-path-row">
              <input
                id="import-path"
                className="input"
                value={manualPath}
                placeholder={t('importPage.file.pathPlaceholder')}
                onChange={(event) => setManualPath(event.target.value)}
              />
              <button className="btn" type="button" onClick={addManualPath}>
                {t('importPage.file.addPath')}
              </button>
              <button className="btn" type="button" onClick={browseFile}>
                {t('importPage.file.browse')}
              </button>
            </div>

            <div
              className="drop-zone"
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleDrop}
            >
              <p className="muted">{t('importPage.file.dropHint')}</p>
              <label className="btn" htmlFor="import-upload">
                {t('importPage.file.chooseFiles')}
              </label>
              <input
                id="import-upload"
                className="visually-hidden"
                type="file"
                multiple
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? [])
                  if (files.length === 0) return
                  setCopyFiles(files)
                  setCopyOpen(true)
                }}
              />
            </div>

            {paths.length > 0 ? (
              <ul className="file-list">
                {paths.map((path) => (
                  <li key={path}>
                    <span>{path}</span>
                    <button
                      className="btn"
                      type="button"
                      aria-label={t('importPage.file.remove', { name: path })}
                      onClick={() =>
                        setPaths((current) => current.filter((item) => item !== path))
                      }
                    >
                      {t('importPage.file.removeLabel')}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            <div className="import-options">
              <label htmlFor="import-mode">
                {t('importPage.file.modeLabel')}
                <select
                  id="import-mode"
                  className="input"
                  value={mode}
                  onChange={(event) =>
                    setMode(
                      event.target.value === 'join'
                        ? 'join'
                        : event.target.value === 'union'
                          ? 'union'
                          : 'independent',
                    )
                  }
                >
                  <option value="independent">
                    {t('importPage.file.modes.independent')}
                  </option>
                  <option value="union">{t('importPage.file.modes.union')}</option>
                  <option value="join">{t('importPage.file.modes.join')}</option>
                </select>
              </label>
              <label htmlFor="import-name">
                {t('importPage.file.nameLabel')}
                <input
                  id="import-name"
                  className="input"
                  value={datasetName}
                  onChange={(event) => setDatasetName(event.target.value)}
                />
              </label>
            </div>

            <div className="import-actions">
              <button
                className="btn"
                type="button"
                onClick={inspectSelected}
                disabled={inspecting || paths.length === 0}
              >
                {inspecting ? t('importPage.file.inspecting') : t('importPage.file.inspect')}
              </button>
              <button className="btn" type="button" onClick={() => setCopyOpen(true)}>
                {t('importPage.file.copyConfirm')}
              </button>
              <button
                className="btn home-primary"
                type="button"
                onClick={startImport}
                disabled={starting}
              >
                {starting ? t('importPage.file.importing') : t('importPage.file.import')}
              </button>
            </div>

            {notice ? <p className="muted">{notice}</p> : null}
            {error ? (
              <p className="error-text" role="alert">
                {error}
              </p>
            ) : null}

            {inspected ? (
              <div className="import-inspect">
                <h3>{t('importPage.file.previewTitle')}</h3>
                <p className="muted">
                  {t('importPage.file.rows', { count: inspected.row_count })} ·{' '}
                  {t('importPage.file.columns', { count: inspected.column_count })}
                  {inspected.sampled ? ` · ${t('importPage.file.sampled')}` : ''}
                </p>
                <div className="table-wrap">
                  <table className="preview-table">
                    <thead>
                      <tr>
                        {inspected.schema_definition.columns.map((column) => (
                          <th key={column.name}>{column.name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {inspected.preview.slice(0, 8).map((row, index) => (
                        <tr key={index}>
                          {inspected.schema_definition.columns.map((column) => (
                            <td key={column.name}>{String(row[column.name] ?? '')}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </section>

          <aside className="import-side">
            {activeJob ? (
              <ImportProgress job={activeJob} onCancel={cancelJob} onRetry={retryJob} />
            ) : (
              <section className="card">
                <h2>{t('importPage.progress.title')}</h2>
                <p className="muted">{t('importPage.progress.idle')}</p>
              </section>
            )}
          </aside>
        </div>
      )}

      {copyOpen ? (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !copying) setCopyOpen(false)
          }}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={t('importPage.file.copyTitle')}
          >
            <h2>{t('importPage.file.copyTitle')}</h2>
            <p className="muted">{t('importPage.file.copyDescription')}</p>
            {copyFiles.length > 0 ? (
              <ul className="file-list">
                {copyFiles.map((file) => (
                  <li key={`${file.name}-${file.size}`}>{file.name}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">{t('importPage.file.chooseFiles')}</p>
            )}
            <label className="btn" htmlFor="copy-upload">
              {t('importPage.file.chooseFiles')}
            </label>
            <input
              id="copy-upload"
              className="visually-hidden"
              type="file"
              multiple
              onChange={(event) => setCopyFiles(Array.from(event.target.files ?? []))}
            />
            <div className="modal-actions">
              <button
                className="btn"
                type="button"
                onClick={() => setCopyOpen(false)}
                disabled={copying}
              >
                {t('common.cancel')}
              </button>
              <button
                className="btn home-primary"
                type="button"
                onClick={copySelected}
                disabled={copying || copyFiles.length === 0}
              >
                {copying ? t('importPage.file.copying') : t('importPage.file.copyConfirm')}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {multiOpen && projectId ? (
        <MultiFileDialog
          projectId={projectId}
          paths={paths}
          onClose={() => setMultiOpen(false)}
          onImported={handleImported}
        />
      ) : null}
    </section>
  )
}
