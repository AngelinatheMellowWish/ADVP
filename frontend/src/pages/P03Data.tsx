import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'

import { computeDatasetAnalysis, type DatasetAnalysis } from '../api/analysis'
import { errorMessage, getDataset, type DatasetDetail } from '../api/projects'
import { QualityPanel } from '../components/QualityPanel'

export function P03Data() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const datasetId = params.get('dataset')
  const [dataset, setDataset] = useState<DatasetDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<DatasetAnalysis | null>(null)
  const [computing, setComputing] = useState(false)

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

            <section className="card">
              <h2>{t('dataPage.previewTitle')}</h2>
              <div className="table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>
                      {dataset.schema_definition.columns.map((column) => (
                        <th key={column.name}>{column.name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {dataset.preview.slice(0, 20).map((row, index) => (
                      <tr key={index}>
                        {dataset.schema_definition.columns.map((column) => (
                          <td key={column.name}>{String(row[column.name] ?? '')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
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
                <Link
                  className="btn home-primary"
                  to={`/projects/${dataset.project_id}/pipeline?dataset=${dataset.id}`}
                >
                  {t('dataPage.startAnalysis')}
                </Link>
              </div>
            </section>
          </aside>
        </div>
      ) : null}
    </section>
  )
}
