import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { TextFact, TextStatsExtraction } from '../api/projects'

export type { TextStatsExtraction }

type Tab = 'long' | 'wide'

type Props = {
  extraction: TextStatsExtraction
  onImport: (shape: Tab, facts: TextFact[]) => void | Promise<void>
  onAIEnhance?: (facts: TextFact[]) => void | Promise<void>
  busy?: boolean
  facts?: TextFact[]
  onFactsChange?: (facts: TextFact[]) => void
  onReset?: () => void
}

function copyFacts(facts: TextFact[]): TextFact[] {
  return facts.map((fact) => ({ ...fact }))
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

function valueOf(fact: TextFact): number | string {
  if (fact.value_number !== null && fact.value_number !== undefined) return fact.value_number
  return fact.value_text ?? ''
}

function snippetOf(fact: TextFact): string {
  const snippet = fact.source?.snippet
  return typeof snippet === 'string' ? snippet : ''
}

function isNumericAIFact(fact: TextFact): boolean {
  return fact.include !== false && Boolean(fact.fact_id) && /\d/.test(snippetOf(fact))
}

function buildWide(
  facts: TextFact[],
  metricLabel: string,
  unitLabel: string,
): { headers: string[]; rows: Record<string, unknown>[] } {
  const included = facts.filter((fact) => fact.include !== false)
  const subjects: string[] = []
  for (const fact of included) {
    if (!subjects.includes(fact.subject_path)) subjects.push(fact.subject_path)
  }
  const headers = [metricLabel, unitLabel, ...subjects]
  const rows: Record<string, unknown>[] = []
  const index = new Map<string, Record<string, unknown>>()
  for (const fact of included) {
    const key = `${fact.metric}\u0000${fact.unit ?? ''}`
    let row = index.get(key)
    if (!row) {
      row = { [metricLabel]: fact.metric, [unitLabel]: fact.unit ?? '' }
      for (const subject of subjects) row[subject] = ''
      index.set(key, row)
      rows.push(row)
    }
    row[fact.subject_path] = valueOf(fact)
  }
  return { headers, rows }
}

export function TextStatsCandidates({
  extraction,
  onImport,
  onAIEnhance,
  busy = false,
  facts: controlledFacts,
  onFactsChange,
  onReset,
}: Props) {
  const { t } = useTranslation()
  const [internalFacts, setInternalFacts] = useState<TextFact[]>(() =>
    copyFacts(extraction.long.facts),
  )
  const [tab, setTab] = useState<Tab>('long')
  const [aiConsent, setAiConsent] = useState(false)
  const [aiConfirmed, setAiConfirmed] = useState(false)
  const controlledRef = useRef(controlledFacts !== undefined)
  controlledRef.current = controlledFacts !== undefined

  useEffect(() => {
    if (!controlledRef.current) setInternalFacts(copyFacts(extraction.long.facts))
    setTab('long')
    setAiConsent(false)
    setAiConfirmed(false)
  }, [extraction])

  const facts = controlledFacts ?? internalFacts
  const wide = useMemo(
    () =>
      buildWide(
        facts,
        t('importPage.document.textStats.metric'),
        t('importPage.document.textStats.unit'),
      ),
    [facts, t],
  )
  const warnings = useMemo(() => {
    const seen = new Set<string>()
    const all = [...extraction.long.warnings, ...extraction.wide.warnings]
    return all.filter((warning) => {
      const key = `${warning.code}:${warning.message}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }, [extraction])
  const included = facts.filter((fact) => fact.include !== false)
  const aiFacts = useMemo(() => facts.filter(isNumericAIFact), [facts])
  const aiSignature = useMemo(
    () =>
      JSON.stringify(
        aiFacts.map((fact) => [
          fact.fact_id,
          fact.subject_path,
          fact.metric,
          fact.value_text,
          fact.unit,
          snippetOf(fact),
        ]),
      ),
    [aiFacts],
  )

  useEffect(() => {
    setAiConfirmed(false)
  }, [aiSignature])

  function commitFacts(next: TextFact[]) {
    if (controlledRef.current && onFactsChange) {
      onFactsChange(next)
    } else {
      setInternalFacts(next)
    }
  }

  function updateFact(index: number, patch: Partial<TextFact>) {
    commitFacts(
      facts.map((fact, rowIndex) => (rowIndex === index ? { ...fact, ...patch } : fact)),
    )
  }

  function updateNumber(index: number, raw: string) {
    const parsed = raw.trim() === '' ? null : Number(raw.replace(/,/g, ''))
    updateFact(index, {
      value_text: raw,
      value_number: parsed !== null && Number.isFinite(parsed) ? parsed : null,
      edited: true,
    })
  }

  function addRow() {
    commitFacts([
      ...facts,
      {
        subject_path: '',
        metric: '',
        value_text: '',
        value_number: null,
        unit: '',
        note: '',
        relation: 'standalone',
        source: {},
        confidence: 0.5,
        include: true,
        edited: true,
      },
    ])
  }

  function removeRow(index: number) {
    commitFacts(facts.filter((_, rowIndex) => rowIndex !== index))
  }

  function resetFacts() {
    if (onReset) {
      onReset()
    } else {
      commitFacts(copyFacts(extraction.long.facts))
    }
    setTab('long')
    setAiConsent(false)
    setAiConfirmed(false)
  }

  function toggleAiConsent(checked: boolean) {
    setAiConsent(checked)
    if (!checked) setAiConfirmed(false)
  }

  return (
    <section className="text-stats-candidates">
      <div className="panel-title">
        <div>
          <strong>{t('importPage.document.textStats.title')}</strong>
          <p className="muted">
            {t('importPage.document.textStats.summary', {
              characters: extraction.char_count,
              paragraphs: extraction.paragraph_count,
              facts: facts.length,
              method:
                extraction.extractor.method === 'rules'
                  ? t('importPage.document.textStats.methodRules')
                  : extraction.extractor.method,
            })}
          </p>
        </div>
        <span className="badge">{extraction.extractor.version}</span>
      </div>

      {warnings.length > 0 ? (
        <ul className="warning-list">
          {warnings.map((warning) => (
            <li key={`${warning.code}-${warning.message}`} className="warning">
              {warning.message}
            </li>
          ))}
        </ul>
      ) : null}

      <div
        className="tab-row"
        role="tablist"
        aria-label={t('importPage.document.textStats.title')}
      >
        <button
          className="tab"
          type="button"
          role="tab"
          aria-selected={tab === 'long'}
          onClick={() => setTab('long')}
        >
          {t('importPage.document.textStats.longTab')}
        </button>
        <button
          className="tab"
          type="button"
          role="tab"
          aria-selected={tab === 'wide'}
          onClick={() => setTab('wide')}
        >
          {t('importPage.document.textStats.wideTab')}
        </button>
      </div>

      {tab === 'long' ? (
        <div>
          <div className="table-wrap">
            <table className="preview-table editable-table">
              <thead>
                <tr>
                  <th>{t('importPage.document.textStats.include')}</th>
                  <th>{t('importPage.document.textStats.subject')}</th>
                  <th>{t('importPage.document.textStats.metric')}</th>
                  <th>{t('importPage.document.textStats.value')}</th>
                  <th>{t('importPage.document.textStats.unit')}</th>
                  <th>{t('importPage.document.textStats.note')}</th>
                  <th>{t('importPage.document.textStats.source')}</th>
                  <th>{t('importPage.document.textStats.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {facts.map((fact, index) => {
                  const snippet = snippetOf(fact)
                  const lineNo =
                    typeof fact.source?.line_no === 'number' ? fact.source.line_no : null
                  const page =
                    typeof fact.source?.page === 'number' ? fact.source.page : null
                  return (
                    <tr key={`${fact.fact_id ?? 'row'}-${index}`}>
                      <td>
                        <input
                          aria-label={`${t('importPage.document.textStats.include')}-${index}`}
                          type="checkbox"
                          checked={fact.include !== false}
                          onChange={(event) =>
                            updateFact(index, { include: event.target.checked })
                          }
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`${t('importPage.document.textStats.subject')}-${index}`}
                          value={fact.subject_path}
                          onChange={(event) =>
                            updateFact(index, {
                              subject_path: event.target.value,
                              edited: true,
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`${t('importPage.document.textStats.metric')}-${index}`}
                          value={fact.metric}
                          onChange={(event) =>
                            updateFact(index, { metric: event.target.value, edited: true })
                          }
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`${t('importPage.document.textStats.value')}-${index}`}
                          value={cellText(valueOf(fact))}
                          onChange={(event) => updateNumber(index, event.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`${t('importPage.document.textStats.unit')}-${index}`}
                          value={fact.unit ?? ''}
                          onChange={(event) =>
                            updateFact(index, { unit: event.target.value, edited: true })
                          }
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`${t('importPage.document.textStats.note')}-${index}`}
                          value={fact.note ?? ''}
                          onChange={(event) =>
                            updateFact(index, { note: event.target.value, edited: true })
                          }
                        />
                      </td>
                      <td data-testid={`fact-source-${index}`}>
                        {snippet ? <span className="source-snippet">{snippet}</span> : null}
                        <span className="muted source-locator">
                          {page !== null
                            ? t('importPage.document.textStats.pageSource', { page })
                            : null}
                          {lineNo !== null
                            ? ` ${t('importPage.document.textStats.lineSource', { line: lineNo })}`
                            : null}
                        </span>
                      </td>
                      <td>
                        <button
                          className="button ghost small"
                          type="button"
                          aria-label={`${t('importPage.document.textStats.deleteRow')}-${index}`}
                          onClick={() => removeRow(index)}
                        >
                          {t('importPage.document.textStats.deleteRow')}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="inline-form">
            <button className="button ghost" type="button" onClick={addRow}>
              {t('importPage.document.textStats.addRow')}
            </button>
            <button className="button" type="button" onClick={resetFacts}>
              {t('importPage.document.textStats.reset')}
            </button>
            <button
              className="button"
              type="button"
              disabled={busy || included.length === 0}
              onClick={() => void onImport('long', included)}
            >
              {t('importPage.document.textStats.importLong')}
            </button>
            <button
              className="button"
              type="button"
              disabled={busy || included.length === 0}
              onClick={() => void onImport('wide', included)}
            >
              {t('importPage.document.textStats.importWide')}
            </button>
          </div>
        </div>
      ) : (
        <div>
          {wide.rows.length === 0 ? (
            <p className="muted">{t('importPage.document.textStats.noWideRows')}</p>
          ) : (
            <div className="table-wrap">
              <table className="preview-table">
                <thead>
                  <tr>
                    {wide.headers.map((header) => (
                      <th key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {wide.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {wide.headers.map((header) => (
                        <td key={header}>{cellText(row[header])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="inline-form">
            <button
              className="button"
              type="button"
              disabled={busy || included.length === 0}
              onClick={() => void onImport('wide', included)}
            >
              {t('importPage.document.textStats.importWide')}
            </button>
            <button
              className="button"
              type="button"
              disabled={busy || included.length === 0}
              onClick={() => void onImport('long', included)}
            >
              {t('importPage.document.textStats.importLong')}
            </button>
          </div>
        </div>
      )}

      {onAIEnhance ? (
        <div className="ai-consent">
          <label>
            <input
              aria-label={t('importPage.document.ai.enable')}
              type="checkbox"
              checked={aiConsent}
              onChange={(event) => toggleAiConsent(event.target.checked)}
            />
            {t('importPage.document.ai.enable')}
          </label>
          <p className="muted">{t('importPage.document.ai.description')}</p>
          {aiConsent ? (
            <div className="ai-preview" data-testid="ai-preview">
              <strong>{t('importPage.document.ai.previewTitle')}</strong>
              {aiFacts.length > 0 ? (
                <ul>
                  {aiFacts.map((fact, index) => (
                    <li key={fact.fact_id ?? index} data-testid={`ai-preview-item-${index}`}>
                      <span>{snippetOf(fact)}</span>
                      <span className="muted">
                        {' · '}
                        {fact.subject_path} · {fact.metric} · {cellText(valueOf(fact))}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">{t('importPage.document.ai.previewEmpty')}</p>
              )}
              <label>
                <input
                  aria-label={t('importPage.document.ai.confirm')}
                  type="checkbox"
                  checked={aiConfirmed}
                  disabled={aiFacts.length === 0}
                  onChange={(event) => setAiConfirmed(event.target.checked)}
                />
                {t('importPage.document.ai.confirm')}
              </label>
            </div>
          ) : null}
          <button
            className="button"
            type="button"
            disabled={busy || !aiConsent || !aiConfirmed || aiFacts.length === 0}
            onClick={() => void onAIEnhance(aiFacts)}
          >
            {t('importPage.document.ai.action')}
          </button>
        </div>
      ) : null}
    </section>
  )
}
