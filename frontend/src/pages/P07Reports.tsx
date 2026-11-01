import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import {
  DEFAULT_REPORT_OUTLINE,
  getPipelineRun,
  getReportManifest,
  getReportMarkdown,
  regeneratePipelineReport,
  reportDownloadUrl,
  reportPackageUrl,
  type PipelineRun,
  type ReportManifest,
  type ReportSection,
} from '../api/pipelines'
import { errorMessage } from '../api/projects'
import { ReportOutline } from '../components/ReportOutline'

export function P07Reports() {
  const { t } = useTranslation()
  const { projectId } = useParams<{ projectId?: string }>()
  const [params] = useSearchParams()
  const runId = params.get('run')

  const [run, setRun] = useState<PipelineRun | null>(null)
  const [manifest, setManifest] = useState<ReportManifest | null>(null)
  const [outline, setOutline] = useState<ReportSection[]>(DEFAULT_REPORT_OUTLINE)
  const [language, setLanguage] = useState<'zh' | 'en'>('zh')
  const [template, setTemplate] = useState<'standard' | 'compact'>('standard')
  const [conclusion, setConclusion] = useState('')
  const [includeChart, setIncludeChart] = useState(true)
  const [includeDerived, setIncludeDerived] = useState(false)
  const [markdown, setMarkdown] = useState('')
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!runId) {
      setRun(null)
      setManifest(null)
      setMarkdown('')
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    getPipelineRun(runId)
      .then(async (detail) => {
        if (cancelled) return
        setRun(detail)
        const report = await getReportManifest(runId)
        if (cancelled) return
        setManifest(report)
        setOutline(report.outline?.length ? report.outline : DEFAULT_REPORT_OUTLINE)
        setLanguage(report.language ?? 'zh')
        setTemplate(report.template ?? 'standard')
        setMarkdown(await getReportMarkdown(runId))
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [runId])

  async function regenerate() {
    if (!runId) return
    setBusy(true)
    setError(null)
    try {
      const result = await regeneratePipelineReport(runId, {
        language,
        template,
        conclusion: conclusion.trim() || null,
        include_chart: includeChart,
        outline,
      })
      const report = result.report.manifest as ReportManifest
      setManifest(report)
      setMarkdown(await getReportMarkdown(runId))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  if (!runId) {
    return (
      <section className="page" data-testid="page-p07">
        <h1>{t('reportPage.title')}</h1>
        <p className="muted">{t('reportPage.missingRun')}</p>
        {projectId ? (
          <Link className="btn" to={`/projects/${projectId}/pipeline`}>
            {t('reportPage.openPipeline')}
          </Link>
        ) : null}
      </section>
    )
  }

  return (
    <section className="page report-page" data-testid="page-p07">
      <header className="import-head">
        <div>
          <h1>{manifest?.dataset_name ?? t('reportPage.title')}</h1>
          <p className="muted">
            {t('reportPage.runLabel')} {runId} · {run?.status ?? '—'}
          </p>
        </div>
        <Link className="btn" to={`/projects/${projectId}/pipeline?run=${runId}`}>
          {t('reportPage.backToPipeline')}
        </Link>
      </header>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {loading ? <p className="muted">{t('reportPage.loading')}</p> : null}

      <div className="report-layout">
        <aside className="card" aria-label={t('reportPage.outline')}>
          <div className="panel-title">
            <div>
              <h2>{t('reportPage.outline')}</h2>
              <p className="muted">{t('reportPage.outlineHint')}</p>
            </div>
          </div>
          <ReportOutline value={outline} onChange={setOutline} disabled={busy} />
        </aside>

        <section className="card" aria-label={t('reportPage.preview')}>
          <div className="panel-title">
            <h2>{t('reportPage.preview')}</h2>
            <span className="badge">{template}</span>
          </div>
          {markdown ? (
            <pre className="report-preview">{markdown}</pre>
          ) : (
            <p className="muted">{t('reportPage.noReport')}</p>
          )}
          {manifest ? (
            <details className="chart-dependent-details">
              <summary>{t('reportPage.manifest')}</summary>
              <pre className="report-preview">
                {JSON.stringify(manifest, null, 2)}
              </pre>
            </details>
          ) : null}
        </section>

        <aside className="card" aria-label={t('reportPage.settings')}>
          <h2>{t('reportPage.settings')}</h2>
          <div className="stack-form">
            <label>
              {t('reportPage.language')}
              <select
                className="input"
                value={language}
                onChange={(event) => setLanguage(event.target.value as 'zh' | 'en')}
              >
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </label>
            <label>
              {t('reportPage.template')}
              <select
                className="input"
                value={template}
                onChange={(event) =>
                  setTemplate(event.target.value as 'standard' | 'compact')
                }
              >
                <option value="standard">{t('reportPage.templates.standard')}</option>
                <option value="compact">{t('reportPage.templates.compact')}</option>
              </select>
            </label>
            <label>
              {t('reportPage.conclusion')}
              <textarea
                rows={3}
                value={conclusion}
                placeholder={t('reportPage.conclusionPlaceholder')}
                onChange={(event) => setConclusion(event.target.value)}
              />
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={includeChart}
                onChange={(event) => setIncludeChart(event.target.checked)}
              />
              {t('reportPage.includeChart')}
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={includeDerived}
                onChange={(event) => setIncludeDerived(event.target.checked)}
              />
              {t('reportPage.includeDerived')}
            </label>
            <button
              type="button"
              className="btn home-primary"
              onClick={() => void regenerate()}
              disabled={busy}
            >
              {busy ? t('reportPage.regenerating') : t('reportPage.regenerate')}
            </button>
          </div>

          <div className="inline-form">
            <a className="btn" href={reportDownloadUrl(runId, 'md')}>
              {t('reportPage.downloadMd')}
            </a>
            <a className="btn" href={reportDownloadUrl(runId, 'html')}>
              {t('reportPage.downloadHtml')}
            </a>
            <a className="btn" href={reportDownloadUrl(runId, 'pdf')}>
              {t('reportPage.downloadPdf')}
            </a>
          </div>
          <div className="inline-form">
            <a
              className="btn"
              href={reportPackageUrl(runId, includeDerived)}
              download
            >
              {t('reportPage.package')}
            </a>
          </div>
          <p className="muted">{t('reportPage.packageHint')}</p>
        </aside>
      </div>
    </section>
  )
}
