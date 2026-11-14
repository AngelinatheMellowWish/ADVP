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
  enhanceTextStats,
  errorMessage,
  importDocument,
  importTextStats,
  inspectDataset,
  inspectDocument,
  type DocumentTablesResponse,
  type ImportOptionsInput,
  type InspectResponse,
  type TextFact,
} from '../api/projects'
import { ImportProgress } from '../components/ImportProgress'
import { MultiFileDialog } from '../components/MultiFileDialog'
import { SqlImportPanel } from '../components/SqlImportPanel'
import { TextStatsCandidates } from '../components/TextStatsCandidates'
import { AdvancedFileOptions } from '../components/import/AdvancedFileOptions'
import { LiveSourceForm } from '../components/import/LiveSourceForm'
import { RemoteSourceForm } from '../components/import/RemoteSourceForm'
import { WebSourceForm } from '../components/import/WebSourceForm'
import {
  DEFAULT_ADVANCED_FILE_OPTIONS,
  isAdvancedFileOptionsValid,
  parseMissingMarkers,
  parseTypeOverrides,
  type AdvancedFileOptionsValue,
} from '../components/import/advancedFileOptionsConfig'

const SOURCE_TABS = ['file', 'database', 'remote', 'document', 'web', 'live'] as const
type SourceTab = (typeof SOURCE_TABS)[number]

type SourceState = 'loading' | 'empty' | 'error' | 'ready'

const TERMINAL: ImportJobStatus[] = ['succeeded', 'failed', 'cancelled']

function copyFacts(facts: TextFact[]): TextFact[] {
  return facts.map((fact) => ({ ...fact }))
}

function isNumericAIFact(fact: TextFact): boolean {
  const snippet = fact.source?.snippet
  return (
    fact.include !== false &&
    Boolean(fact.fact_id) &&
    typeof snippet === 'string' &&
    /\d/.test(snippet)
  )
}

function mergeDocumentFacts(
  previous: TextFact[] | null,
  extracted: TextFact[],
): TextFact[] {
  if (!previous) return copyFacts(extracted)
  const byId = new Map<string, TextFact>()
  for (const fact of previous) {
    if (fact.fact_id) byId.set(fact.fact_id, fact)
  }
  return extracted.map((fact) => {
    const prior = fact.fact_id ? byId.get(fact.fact_id) : undefined
    if (!prior) return { ...fact }
    return {
      ...fact,
      subject_path: prior.subject_path,
      metric: prior.metric,
      value_text: prior.value_text,
      value_number: prior.value_number,
      value_low: prior.value_low,
      value_high: prior.value_high,
      unit: prior.unit,
      qualifier: prior.qualifier,
      relation: prior.relation,
      note: prior.note,
      include: prior.include,
      edited: prior.edited,
    }
  })
}

function applyAIResult(
  current: TextFact[],
  sent: TextFact[],
  enhanced: TextFact[],
): TextFact[] {
  const sentIds = new Set(
    sent.map((fact) => fact.fact_id).filter((id): id is string => Boolean(id)),
  )
  const enhancedById = new Map<string, TextFact>()
  for (const fact of enhanced) {
    if (fact.fact_id) enhancedById.set(fact.fact_id, fact)
  }
  const next: TextFact[] = []
  for (const fact of current) {
    if (fact.fact_id && sentIds.has(fact.fact_id)) {
      const updated = enhancedById.get(fact.fact_id)
      if (updated) next.push({ ...fact, ...updated })
    } else {
      next.push(fact)
    }
  }
  return next
}

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
  const [jobs, setJobs] = useState<ImportJobDetail[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copyOpen, setCopyOpen] = useState(false)
  const [copyFiles, setCopyFiles] = useState<File[]>([])
  const [copying, setCopying] = useState(false)
  const [multiOpen, setMultiOpen] = useState(false)
  const [docPath, setDocPath] = useState('')
  const [docName, setDocName] = useState('')
  const [docResult, setDocResult] = useState<DocumentTablesResponse | null>(null)
  const [docFacts, setDocFacts] = useState<TextFact[] | null>(null)
  const [docBaselineFacts, setDocBaselineFacts] = useState<TextFact[] | null>(null)
  const [docInspectedPath, setDocInspectedPath] = useState('')
  const [docAI, setDocAI] = useState<Record<string, unknown> | null>(null)
  const [docBusy, setDocBusy] = useState<string | null>(null)
  const [docError, setDocError] = useState<string | null>(null)
  const [advancedOptions, setAdvancedOptions] = useState<AdvancedFileOptionsValue>(
    DEFAULT_ADVANCED_FILE_OPTIONS,
  )
  const [advancedDirty, setAdvancedDirty] = useState(false)
  const [databaseState, setDatabaseState] = useState<SourceState>('empty')
  const [remoteState, setRemoteState] = useState<SourceState>('empty')
  const [webState, setWebState] = useState<SourceState>('empty')
  const [liveState, setLiveState] = useState<SourceState>('empty')

  useEffect(() => {
    if (jobs.length === 0 || jobs.every((job) => TERMINAL.includes(job.status))) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      Promise.all(
        jobs.map((job) => (TERMINAL.includes(job.status) ? job : getImportJob(job.id))),
      )
        .then((updated) => {
          if (cancelled) return
          setJobs(updated)
          if (
            updated.length === 1 &&
            updated[0].status === 'succeeded' &&
            updated[0].result_dataset_id &&
            projectId
          ) {
            navigate(`/projects/${projectId}/data?dataset=${updated[0].result_dataset_id}`)
          }
        })
        .catch((caught: unknown) => {
          if (!cancelled) setError(errorMessage(caught))
        })
    }, 400)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [jobs, navigate, projectId])

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

  function changeAdvancedOptions(next: AdvancedFileOptionsValue) {
    setAdvancedOptions(next)
    setAdvancedDirty(true)
  }

  function resetAdvancedOptions() {
    setAdvancedOptions(DEFAULT_ADVANCED_FILE_OPTIONS)
    setAdvancedDirty(false)
  }

  function buildImportOptions(path: string): ImportOptionsInput {
    const options: ImportOptionsInput = {}
    if (advancedDirty) {
      options.has_header = advancedOptions.hasHeader
      options.sample_rows = advancedOptions.sampleRows
    }
    const encoding = advancedOptions.encoding.trim()
    if (encoding) options.encoding = encoding
    if (advancedOptions.delimiter) options.delimiter = advancedOptions.delimiter
    const sheetOrVariable = advancedOptions.sheetOrVariable.trim()
    if (sheetOrVariable) {
      if (/\.(xlsx|xls)$/i.test(path)) {
        const sheetIndex = Number(sheetOrVariable)
        options.sheet = Number.isInteger(sheetIndex) ? sheetIndex : sheetOrVariable
      } else {
        options.variable = sheetOrVariable
      }
    }
    const missingValues = parseMissingMarkers(advancedOptions.missingMarkers)
    if (missingValues.length > 0) options.missing_values = missingValues
    const typeOverrides = parseTypeOverrides(advancedOptions.typeOverrides)
    if (Object.keys(typeOverrides).length > 0) options.type_overrides = typeOverrides
    return options
  }

  function sourceState(source: SourceTab): SourceState {
    if (source === 'file') {
      if (inspecting || starting) return 'loading'
      if (error && !inspected) return 'error'
      if (inspected) return inspected.row_count > 0 ? 'ready' : 'empty'
      return paths.length > 0 ? 'ready' : 'empty'
    }
    if (source === 'document') {
      if (docBusy) return 'loading'
      if (docError) return 'error'
      if (docResult) return 'ready'
      return 'empty'
    }
    if (source === 'database') return databaseState
    if (source === 'remote') return remoteState
    if (source === 'web') return webState
    if (source === 'live') return liveState
    return 'empty'
  }

  async function inspectSelected() {
    if (!projectId || paths.length === 0) {
      setError(t('importPage.file.emptyPaths'))
      return
    }
    if (!isAdvancedFileOptionsValid(advancedOptions)) {
      setError(t('importPage.file.advanced.invalid'))
      return
    }
    setInspecting(true)
    setError(null)
    setInspected(null)
    try {
      setInspected(await inspectDataset(projectId, paths[0], buildImportOptions(paths[0])))
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
    if (!isAdvancedFileOptionsValid(advancedOptions)) {
      setError(t('importPage.file.advanced.invalid'))
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
            buildImportOptions(path),
          ),
        )
      }
      setJobs(jobs)
      if (jobs.length > 1) {
        setNotice(t('importPage.file.queuedOthers', { count: jobs.length - 1 }))
      }
    } catch (caught) {
      setError(`${t('importPage.file.importFailed')} ${errorMessage(caught)}`)
    } finally {
      setStarting(false)
    }
  }

  async function cancelJob(jobId: string) {
    try {
      const updated = await cancelImportJob(jobId)
      setJobs((current) => current.map((job) => (job.id === jobId ? updated : job)))
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  async function retryJob(jobId: string) {
    try {
      const updated = await retryImportJob(jobId)
      setJobs((current) => current.map((job) => (job.id === jobId ? updated : job)))
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
    const path = docPath.trim()
    if (!projectId || !path) {
      setDocError(t('importPage.document.needsPath'))
      return
    }
    setDocBusy('inspect')
    setDocError(null)
    try {
      const result = await inspectDocument(projectId, path)
      const extracted = result.text ? copyFacts(result.text.long.facts) : []
      const samePath = path === docInspectedPath
      setDocResult(result)
      setDocBaselineFacts(copyFacts(extracted))
      setDocFacts((current) =>
        samePath && current ? mergeDocumentFacts(current, extracted) : copyFacts(extracted),
      )
      setDocInspectedPath(path)
      setDocAI(null)
    } catch (caught) {
      setDocError(`${t('importPage.document.failed')} ${errorMessage(caught)}`)
    } finally {
      setDocBusy(null)
    }
  }

  function resetDocumentFacts() {
    setDocFacts(docBaselineFacts ? copyFacts(docBaselineFacts) : null)
    setDocAI(null)
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

  async function importDocumentText(shape: 'long' | 'wide', facts: TextFact[]) {
    if (!projectId || !docResult?.text || !docPath.trim()) return
    const selected = facts.filter((fact) => fact.include !== false)
    if (selected.length === 0) return
    setDocBusy(`text-${shape}`)
    setDocError(null)
    try {
      const dataset = await importTextStats(
        projectId,
        docPath.trim(),
        docResult.source_sha256,
        shape,
        selected,
        docName.trim() || undefined,
        docAI,
      )
      navigate(`/projects/${projectId}/data?dataset=${dataset.id}`)
    } catch (caught) {
      setDocError(`${t('importPage.document.failed')} ${errorMessage(caught)}`)
    } finally {
      setDocBusy(null)
    }
  }

  async function enhanceDocumentText(facts: TextFact[]) {
    if (!projectId || !docResult?.text || !docPath.trim()) return
    const numeric = facts.filter(isNumericAIFact)
    if (numeric.length === 0) return
    setDocBusy('ai')
    setDocError(null)
    try {
      const result = await enhanceTextStats(
        projectId,
        docPath.trim(),
        docResult.source_sha256,
        numeric,
      )
      setDocFacts((current) =>
        current
          ? applyAIResult(current, numeric, result.facts)
          : copyFacts(result.facts),
      )
      setDocResult((current) =>
        current?.text
          ? {
              ...current,
              text: {
                ...current.text,
                long: { ...current.text.long, warnings: result.warnings },
                wide: { ...current.text.wide, warnings: result.warnings },
              },
            }
          : current,
      )
      const ai = result.ai as { used?: boolean; model?: string | null }
      setDocAI(ai.used ? result.ai : null)
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

      <p
        className={`source-state source-state-${sourceState(tab)}`}
        data-testid={`source-state-${tab}`}
        role="status"
      >
        {t(`importPage.states.${sourceState(tab)}`)}
      </p>

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
                  <TextStatsCandidates
                    extraction={docResult.text}
                    facts={docFacts ?? docResult.text.long.facts}
                    onFactsChange={setDocFacts}
                    onReset={resetDocumentFacts}
                    onImport={importDocumentText}
                    onAIEnhance={enhanceDocumentText}
                    busy={docBusy !== null}
                  />
                </section>
              ) : (
                <p className="muted">{t('importPage.document.noText')}</p>
              )}
            </div>
          ) : null}
        </section>
      ) : tab === 'database' ? (
        projectId ? (
          <SqlImportPanel
            projectId={projectId}
            onImported={handleImported}
            onStateChange={setDatabaseState}
          />
        ) : (
          <section className="card">
            <p className="muted">{t('importPage.database.needsProject')}</p>
          </section>
        )
      ) : tab === 'remote' ? (
        projectId ? (
          <RemoteSourceForm
            projectId={projectId}
            onImported={handleImported}
            onStateChange={setRemoteState}
          />
        ) : (
          <section className="card">
            <p className="muted">{t('importPage.database.needsProject')}</p>
          </section>
        )
      ) : tab === 'web' ? (
        projectId ? (
          <WebSourceForm
            projectId={projectId}
            onImported={handleImported}
            onStateChange={setWebState}
          />
        ) : (
          <section className="card">
            <p className="muted">{t('importPage.database.needsProject')}</p>
          </section>
        )
      ) : tab === 'live' ? (
        projectId ? (
          <LiveSourceForm
            projectId={projectId}
            onImported={handleImported}
            onStateChange={setLiveState}
          />
        ) : (
          <section className="card">
            <p className="muted">{t('importPage.database.needsProject')}</p>
          </section>
        )
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

            <AdvancedFileOptions
              values={advancedOptions}
              onChange={changeAdvancedOptions}
              onReset={resetAdvancedOptions}
            />

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
                {inspected.issues.length > 0 ? (
                  <ul className="import-issues">
                    {inspected.issues.map((issue, index) => (
                      <li
                        key={`${issue.code}-${issue.column ?? 'general'}-${index}`}
                        className={issue.severity === 'warning' ? 'warning' : 'muted'}
                      >
                        {issue.message}
                      </li>
                    ))}
                  </ul>
                ) : null}
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
            {jobs.length > 0 ? (
              <div className="import-job-list">
                {jobs.map((job) => (
                  <ImportProgress
                    key={job.id}
                    job={job}
                    label={String(job.payload.path ?? '')}
                    onCancel={() => void cancelJob(job.id)}
                    onRetry={() => void retryJob(job.id)}
                  />
                ))}
              </div>
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
