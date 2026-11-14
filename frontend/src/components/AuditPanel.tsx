import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  auditExportUrl,
  listAuditEvents,
  type AuditEvent,
  type AuditFilters,
} from '../api/audit'
import { errorMessage } from '../api/projects'

export function AuditPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<AuditFilters>({ projectId })
  const [applied, setApplied] = useState<AuditFilters>({ projectId })
  const [rows, setRows] = useState<AuditEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (filters: AuditFilters) => {
    setLoading(true)
    setError(null)
    try {
      const items = await listAuditEvents(filters)
      setRows(Array.isArray(items) ? items : [])
      setCopied(false)
    } catch (caught) {
      setError(errorMessage(caught))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load({ projectId })
  }, [load, projectId])

  function update<K extends keyof AuditFilters>(key: K, value: AuditFilters[K]) {
    setDraft((current) => ({ ...current, [key]: value }))
  }

  function apply(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next: AuditFilters = { ...draft, projectId }
    setApplied(next)
    void load(next)
  }

  async function copyDiagnostics() {
    const lines = [
      'ADVP audit diagnostics',
      `project: ${projectId}`,
      ...rows.map(
        (row) =>
          `${row.created_at ?? '—'} ${row.event} ${row.target_type ?? ''}/${
            row.target_id ?? ''
          } ${JSON.stringify(row.detail)}`,
      ),
    ]
    try {
      await navigator.clipboard.writeText(lines.join('\n'))
      setCopied(true)
    } catch {
      setError('无法访问剪贴板，请手动选择内容复制')
    }
  }

  return (
    <section className="audit-panel" data-testid="audit-panel">
      <div className="panel-title">
        <div>
          <h4>{t('tracePage.audit.title')}</h4>
          <p className="muted">project: {projectId}</p>
        </div>
        <div className="inline-form">
          <a className="button" href={auditExportUrl('json', applied)}>
            {t('tracePage.audit.exportJson')}
          </a>
          <a className="button" href={auditExportUrl('csv', applied)}>
            {t('tracePage.audit.exportCsv')}
          </a>
          <button className="button" onClick={() => void copyDiagnostics()}>
            {t('tracePage.audit.copyDiagnostics')}
          </button>
        </div>
      </div>

      <form className="inline-form" onSubmit={apply}>
        <label>
          {t('tracePage.audit.event')}
          <input
            value={draft.event ?? ''}
            onChange={(event) => update('event', event.target.value)}
          />
        </label>
        <label>
          {t('tracePage.audit.target')}
          <input
            value={draft.target ?? ''}
            onChange={(event) => update('target', event.target.value)}
          />
        </label>
        <label>
          {t('tracePage.audit.keyword')}
          <input
            value={draft.keyword ?? ''}
            onChange={(event) => update('keyword', event.target.value)}
          />
        </label>
        <label>
          {t('tracePage.audit.since')}
          <input
            type="datetime-local"
            value={draft.since ?? ''}
            onChange={(event) => update('since', event.target.value)}
          />
        </label>
        <label>
          {t('tracePage.audit.until')}
          <input
            type="datetime-local"
            value={draft.until ?? ''}
            onChange={(event) => update('until', event.target.value)}
          />
        </label>
        <button className="button" type="submit">
          {t('tracePage.audit.apply')}
        </button>
      </form>

      {copied ? <p className="muted">{t('tracePage.audit.copied')}</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {loading ? <p className="muted">…</p> : null}
      {!loading && rows.length === 0 ? (
        <p className="muted">{t('tracePage.audit.noEvents')}</p>
      ) : null}
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table className="preview-table">
            <thead>
              <tr>
                <th>{t('tracePage.audit.time')}</th>
                <th>{t('tracePage.audit.event')}</th>
                <th>{t('tracePage.audit.target')}</th>
                <th>{t('tracePage.audit.detail')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} data-testid={`audit-row-${row.id}`}>
                  <td>{row.created_at ?? '—'}</td>
                  <td>{row.event}</td>
                  <td>
                    {row.target_type ?? '—'}
                    {row.target_id ? ` / ${row.target_id}` : ''}
                  </td>
                  <td>
                    <code>{JSON.stringify(row.detail)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
