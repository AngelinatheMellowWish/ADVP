import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'

import { computeDatasetAnalysis, type DatasetAnalysis } from '../api/analysis'
import {
  errorMessage,
  exportSampleCsv,
  getDataset,
  getPreview,
  reprofileDataset,
  updateProfileOverrides,
  type ColumnProfile,
  type DatasetDetail,
} from '../api/projects'
import { listProviders, type Provider } from '../api/providers'
import { AnalysisCharts } from '../components/AnalysisCharts'
import { AiContextPreview } from '../components/AiContextPreview'
import { QualityPanel } from '../components/QualityPanel'

const PAGE_SIZE = 10
const TYPE_OVERRIDE_TYPES = ['int', 'float', 'string', 'bool', 'date', 'datetime'] as const

export function P03Data() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const datasetId = params.get('dataset')
  const [dataset, setDataset] = useState<DatasetDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<DatasetAnalysis | null>(null)
  const [computing, setComputing] = useState(false)
  const [providers, setProviders] = useState<Provider[]>([])
  const [showContext, setShowContext] = useState(false)
  const [page, setPage] = useState(0)
  const [pagedRows, setPagedRows] = useState<Record<string, unknown>[] | null>(null)
  const [paging, setPaging] = useState(false)
  const [sensitiveColumns, setSensitiveColumns] = useState<string[]>([])
  const [typeOverrides, setTypeOverrides] = useState<Record<string, string>>({})
  const [savingOverrides, setSavingOverrides] = useState(false)
  const [reprofiling, setReprofiling] = useState(false)
  const [overrideNotice, setOverrideNotice] = useState<string | null>(null)
  const [exportRows, setExportRows] = useState<'1000' | '10000' | '100000' | 'full'>('1000')
  const [exportConfirm, setExportConfirm] = useState(false)
  const [exporting, setExporting] = useState(false)

  const load = useCallback(() => {
    if (!datasetId) {
      setDataset(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    getDataset(datasetId)
      .then((data) => {
        if (!cancelled) setDataset(data)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(`${t('dataPage.loadFailed')} ${errorMessage(caught)}`)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [datasetId, t])

  useEffect(() => load(), [load])

  useEffect(() => {
    let cancelled = false
    listProviders()
      .then((data) => {
        if (!cancelled) setProviders(data)
      })
      .catch(() => {
        if (!cancelled) setProviders([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    setPage(0)
    setPagedRows(null)
  }, [datasetId])

  useEffect(() => {
    if (!dataset) return
    setSensitiveColumns(
      dataset.profile.columns.filter((column) => column.sensitive).map((column) => column.name),
    )
    const raw = dataset.options.profile_overrides
    const stored =
      raw && typeof raw === 'object'
        ? (raw as Record<string, unknown>).type_overrides
        : undefined
    setTypeOverrides(
      stored && typeof stored === 'object'
        ? Object.fromEntries(
            Object.entries(stored).map(([column, value]) => [column, String(value)]),
          )
        : {},
    )
  }, [dataset])

  function statText(value: unknown): string {
    if (typeof value === 'number' && Number.isFinite(value)) {
      return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100)
    }
    return '—'
  }

  function headerStats(profile: ColumnProfile | undefined): string | null {
    if (!profile) return null
    const stats = profile.stats
    if (['integer', 'number', 'geo_coordinate'].includes(profile.semantic_type)) {
      if (stats.mean !== undefined || stats.min !== undefined || stats.max !== undefined) {
        return t('dataPage.headerStatNumeric', {
          mean: statText(stats.mean),
          min: statText(stats.min),
          max: statText(stats.max),
        })
      }
    }
    if (['date', 'datetime', 'time'].includes(profile.semantic_type)) {
      if (stats.min !== undefined || stats.max !== undefined) {
        return t('dataPage.headerStatRange', {
          min: statText(stats.min),
          max: statText(stats.max),
        })
      }
    }
    if (stats.min_length !== undefined || stats.max_length !== undefined) {
      return t('dataPage.headerStatText', {
        min: statText(stats.min_length),
        max: statText(stats.max_length),
        avg: statText(stats.avg_length),
      })
    }
    return null
  }

  async function changePage(next: number) {
    if (!dataset) return
    const total = Math.max(
      1,
      Math.ceil(Math.max(dataset.row_count, dataset.preview.length) / PAGE_SIZE),
    )
    if (next < 0 || next >= total) return
    setPaging(true)
    setError(null)
    try {
      if (next === 0) {
        setPagedRows(null)
      } else {
        const response = await getPreview(dataset.id, PAGE_SIZE, next * PAGE_SIZE)
        setPagedRows(response.rows)
      }
      setPage(next)
    } catch (caught) {
      setError(`${t('dataPage.previewFailed')} ${errorMessage(caught)}`)
    } finally {
      setPaging(false)
    }
  }

  function toggleSensitive(column: string, checked: boolean) {
    setSensitiveColumns((current) =>
      checked
        ? [...current.filter((item) => item !== column), column]
        : current.filter((item) => item !== column),
    )
  }

  function changeTypeOverride(column: string, value: string) {
    setTypeOverrides((current) => {
      const next = { ...current }
      if (value) {
        next[column] = value
      } else {
        delete next[column]
      }
      return next
    })
  }

  async function saveOverrides() {
    if (!dataset) return
    setSavingOverrides(true)
    setError(null)
    setOverrideNotice(null)
    try {
      await updateProfileOverrides(dataset.id, {
        sensitive_columns: sensitiveColumns,
        type_overrides: typeOverrides,
      })
      setOverrideNotice(t('dataPage.overridesSaved'))
      load()
    } catch (caught) {
      setError(`${t('dataPage.overridesFailed')} ${errorMessage(caught)}`)
    } finally {
      setSavingOverrides(false)
    }
  }

  async function recomputeStatistics() {
    if (!dataset) return
    setReprofiling(true)
    setError(null)
    setOverrideNotice(null)
    try {
      await reprofileDataset(dataset.id)
      setOverrideNotice(t('dataPage.reprofileDone'))
      load()
    } catch (caught) {
      setError(`${t('dataPage.reprofileFailed')} ${errorMessage(caught)}`)
    } finally {
      setReprofiling(false)
    }
  }

  function downloadBlob(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = name
    link.click()
    URL.revokeObjectURL(url)
  }

  async function exportCsv(rows: number | 'full') {
    if (!dataset) return
    if (rows === 'full' && !exportConfirm) {
      setExportConfirm(true)
      return
    }
    setExporting(true)
    setError(null)
    try {
      const blob = await exportSampleCsv(dataset.id, rows)
      downloadBlob(
        blob,
        `${dataset.name.replace(/[^\w.-]+/g, '-') || 'sample'}-sample.csv`,
      )
      setExportConfirm(false)
    } catch (caught) {
      setError(`${t('dataPage.exportFailed')} ${errorMessage(caught)}`)
    } finally {
      setExporting(false)
    }
  }

  async function computeAnalysis() {
    if (!dataset) return
    setComputing(true)
    setError(null)
    try {
      setAnalysis((await computeDatasetAnalysis(dataset.id)).analysis)
    } catch (caught) {
      setError(`${t('dataPage.analysisFailed')} ${errorMessage(caught)}`)
    } finally {
      setComputing(false)
    }
  }

  const totalPages = dataset
    ? Math.max(
        1,
        Math.ceil(Math.max(dataset.row_count, dataset.preview.length) / PAGE_SIZE),
      )
    : 1
  const previewRows = dataset
    ? page === 0 || !pagedRows
      ? dataset.preview.slice(0, PAGE_SIZE)
      : pagedRows
    : []

  if (!datasetId) {
    return (
      <section className="page" data-testid="page-p03">
        <h1>{t('dataPage.title')}</h1>
        <p className="muted">{t('dataPage.missing')}</p>
      </section>
    )
  }

  return (
    <section className="page data-page" data-testid="page-p03">
      <header className="import-head">
        <h1>{dataset?.name ?? t('dataPage.title')}</h1>
        {dataset ? (
          <p className="muted">
            {t('dataPage.rows', { count: dataset.row_count })} ·{' '}
            {t('dataPage.columns', { count: dataset.column_count })}
            {dataset.sampled ? ` · ${t('dataPage.sampled')}` : ''}
          </p>
        ) : null}
      </header>

      {loading ? <p className="muted">{t('dataPage.loading')}</p> : null}
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}

      {dataset ? (
        <div className="data-layout">
          <div className="data-main">
            <QualityPanel dataset={dataset} onChanged={() => load()} />

            <AnalysisCharts dataset={dataset} analysis={analysis} />

            <section className="card">
              <h2>{t('dataPage.fieldsTitle')}</h2>
              <div className="table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>
                      <th>{t('dataPage.fieldName')}</th>
                      <th>{t('dataPage.fieldType')}</th>
                      <th>{t('dataPage.fieldMissing')}</th>
                      <th>{t('dataPage.fieldUnique')}</th>
                      <th>{t('dataPage.fieldSensitive')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dataset.schema_definition.columns.map((column) => {
                      const profile = dataset.profile.columns.find(
                        (item) => item.name === column.name,
                      )
                      return (
                        <tr key={column.name}>
                          <td>{column.name}</td>
                          <td>{column.semantic_type}</td>
                          <td>
                            {profile
                              ? `${Math.round(profile.null_rate * 1000) / 10}%`
                              : '—'}
                          </td>
                          <td>{profile ? profile.n_unique : column.cardinality}</td>
                          <td>{profile?.sensitive ? '✓' : '—'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="card" data-testid="profile-overrides">
              <h2>{t('dataPage.overridesTitle')}</h2>
              <p className="muted">{t('dataPage.overridesHint')}</p>
              <h3>{t('dataPage.sensitiveTitle')}</h3>
              <div className="override-columns">
                {dataset.schema_definition.columns.map((column) => (
                  <label key={column.name} className="override-option">
                    <input
                      type="checkbox"
                      aria-label={t('dataPage.sensitiveColumn', { column: column.name })}
                      checked={sensitiveColumns.includes(column.name)}
                      onChange={(event) =>
                        toggleSensitive(column.name, event.target.checked)
                      }
                    />
                    <span>{column.name}</span>
                  </label>
                ))}
              </div>
              <h3>{t('dataPage.typeOverridesTitle')}</h3>
              <div className="override-columns">
                {dataset.schema_definition.columns.map((column) => (
                  <label key={column.name} className="override-option">
                    <span>{column.name}</span>
                    <select
                      aria-label={t('dataPage.typeOverrideFor', { column: column.name })}
                      value={typeOverrides[column.name] ?? ''}
                      onChange={(event) =>
                        changeTypeOverride(column.name, event.target.value)
                      }
                    >
                      <option value="">{t('dataPage.typeAuto')}</option>
                      {TYPE_OVERRIDE_TYPES.map((typeName) => (
                        <option key={typeName} value={typeName}>
                          {t(`dataPage.types.${typeName}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
              <div className="import-actions">
                <button
                  className="btn"
                  type="button"
                  onClick={saveOverrides}
                  disabled={savingOverrides}
                >
                  {savingOverrides
                    ? t('dataPage.savingOverrides')
                    : t('dataPage.saveOverrides')}
                </button>
                <button
                  className="btn"
                  type="button"
                  onClick={recomputeStatistics}
                  disabled={reprofiling}
                >
                  {reprofiling ? t('dataPage.reprofiling') : t('dataPage.reprofile')}
                </button>
              </div>
              {overrideNotice ? (
                <p className="muted" role="status">
                  {overrideNotice}
                </p>
              ) : null}
            </section>

            <section className="card">
              <h2>{t('dataPage.previewTitle')}</h2>
              <div className="table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>
                      {dataset.schema_definition.columns.map((column) => {
                        const profile = dataset.profile.columns.find(
                          (item) => item.name === column.name,
                        )
                        const stats = headerStats(profile)
                        return (
                          <th key={column.name} title={stats ?? undefined}>
                            <div>{column.name}</div>
                            {stats ? (
                              <small
                                className="muted th-stats"
                                data-testid={`header-stats-${column.name}`}
                              >
                                {stats}
                              </small>
                            ) : null}
                          </th>
                        )
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row, index) => (
                      <tr key={`${page}-${index}`}>
                        {dataset.schema_definition.columns.map((column) => (
                          <td key={column.name}>{String(row[column.name] ?? '')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="pagination import-actions">
                <button
                  className="btn"
                  type="button"
                  aria-label={t('dataPage.previousPage')}
                  onClick={() => changePage(page - 1)}
                  disabled={page === 0 || paging}
                >
                  {t('dataPage.previousPage')}
                </button>
                <span className="muted" data-testid="preview-page">
                  {t('dataPage.pageInfo', { page: page + 1, total: totalPages })}
                </span>
                <button
                  className="btn"
                  type="button"
                  aria-label={t('dataPage.nextPage')}
                  onClick={() => changePage(page + 1)}
                  disabled={page + 1 >= totalPages || paging}
                >
                  {t('dataPage.nextPage')}
                </button>
              </div>
            </section>
          </div>

          <aside className="data-side">
            <section className="card">
              <h2>{t('dataPage.analysisTitle')}</h2>
              {analysis ? (
                <p className="muted">
                  {t('dataPage.analysisSummary', { size: analysis.sample_size })}
                </p>
              ) : (
                <p className="muted">{t('dataPage.analysisTitle')}</p>
              )}
              <div className="import-actions">
                <button
                  className="btn"
                  type="button"
                  onClick={computeAnalysis}
                  disabled={computing}
                >
                  {computing ? t('dataPage.computing') : t('dataPage.computeAnalysis')}
                </button>
                <button
                  className="btn"
                  type="button"
                  onClick={() => setShowContext(true)}
                >
                  {t('dataPage.aiContext')}
                </button>
                <Link
                  className="btn home-primary"
                  to={`/projects/${dataset.project_id}/pipeline?dataset=${dataset.id}`}
                >
                  {t('dataPage.startAnalysis')}
                </Link>
              </div>
            </section>

            <section className="card">
              <h2>{t('dataPage.exportTitle')}</h2>
              <p className="muted">{t('dataPage.exportHint')}</p>
              <label htmlFor="export-rows">{t('dataPage.exportRows')}</label>
              <select
                id="export-rows"
                className="input"
                value={exportRows}
                onChange={(event) =>
                  setExportRows(
                    event.target.value as '1000' | '10000' | '100000' | 'full',
                  )
                }
              >
                <option value="1000">{t('dataPage.exportRowOptions.1000')}</option>
                <option value="10000">{t('dataPage.exportRowOptions.10000')}</option>
                <option value="100000">{t('dataPage.exportRowOptions.100000')}</option>
                <option value="full">{t('dataPage.exportRowOptions.full')}</option>
              </select>
              <div className="import-actions">
                <button
                  className="btn"
                  type="button"
                  onClick={() =>
                    void exportCsv(exportRows === 'full' ? 'full' : Number(exportRows))
                  }
                  disabled={exporting}
                >
                  {exporting ? t('dataPage.exporting') : t('dataPage.exportCsv')}
                </button>
                <button
                  className="btn"
                  type="button"
                  data-reason="parquet_export_unavailable"
                  title={t('dataPage.parquetUnavailable')}
                  disabled
                >
                  {t('dataPage.exportParquet')}
                </button>
              </div>
              <p className="muted">{t('dataPage.parquetUnavailable')}</p>
            </section>
          </aside>
        </div>
      ) : null}

      {dataset && showContext ? (
        <AiContextPreview
          dataset={dataset}
          providers={providers}
          onClose={() => setShowContext(false)}
        />
      ) : null}

      {exportConfirm ? (
        <div className="modal-backdrop">
          <div className="modal" role="dialog" aria-modal="true">
            <h2>{t('dataPage.exportFullTitle')}</h2>
            <p className="muted">{t('dataPage.exportFullHint')}</p>
            <div className="modal-actions">
              <button className="btn" type="button" onClick={() => setExportConfirm(false)}>
                {t('common.cancel')}
              </button>
              <button
                className="btn home-primary"
                type="button"
                onClick={() => void exportCsv('full')}
                disabled={exporting}
              >
                {t('dataPage.exportFullConfirm')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
