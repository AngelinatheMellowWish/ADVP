import { useEffect, useMemo, useState } from 'react'

import type { TextFact, TextStatsExtraction } from '../api/projects'

export type { TextStatsExtraction }

type Tab = 'long' | 'wide'

type Props = {
  extraction: TextStatsExtraction
  onImport: (shape: Tab, facts: TextFact[]) => void | Promise<void>
  onAIEnhance?: (facts: TextFact[]) => void | Promise<void>
  busy?: boolean
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

function valueOf(fact: TextFact): number | string {
  if (fact.value_number !== null && fact.value_number !== undefined) return fact.value_number
  return fact.value_text ?? ''
}

function buildWide(facts: TextFact[]): { headers: string[]; rows: Record<string, unknown>[] } {
  const included = facts.filter((fact) => fact.include !== false)
  const subjects: string[] = []
  for (const fact of included) {
    if (!subjects.includes(fact.subject_path)) subjects.push(fact.subject_path)
  }
  const headers = ['指标', '单位', ...subjects]
  const rows: Record<string, unknown>[] = []
  const index = new Map<string, Record<string, unknown>>()
  for (const fact of included) {
    const key = `${fact.metric}\u0000${fact.unit ?? ''}`
    let row = index.get(key)
    if (!row) {
      row = { 指标: fact.metric, 单位: fact.unit ?? '' }
      for (const subject of subjects) row[subject] = ''
      index.set(key, row)
      rows.push(row)
    }
    row[fact.subject_path] = valueOf(fact)
  }
  return { headers, rows }
}

export function TextStatsCandidates({ extraction, onImport, onAIEnhance, busy = false }: Props) {
  const [facts, setFacts] = useState<TextFact[]>(() =>
    extraction.long.facts.map((fact) => ({ ...fact })),
  )
  const [tab, setTab] = useState<Tab>('long')
  const [aiConsent, setAiConsent] = useState(false)

  useEffect(() => {
    setFacts(extraction.long.facts.map((fact) => ({ ...fact })))
    setTab('long')
    setAiConsent(false)
  }, [extraction])

  const wide = useMemo(() => buildWide(facts), [facts])
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

  function updateFact(index: number, patch: Partial<TextFact>) {
    setFacts((current) =>
      current.map((fact, rowIndex) => (rowIndex === index ? { ...fact, ...patch } : fact)),
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
    setFacts((current) => [
      ...current,
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
    setFacts((current) => current.filter((_, rowIndex) => rowIndex !== index))
  }

  return (
    <section className="text-stats-candidates">
      <div className="panel-title">
        <div>
          <strong>文本统计候选</strong>
          <p className="muted">
            {extraction.char_count} 字符 · {extraction.paragraph_count} 段 · {facts.length} 条事实 ·{' '}
            {extraction.extractor.method === 'rules' ? '本地规则' : extraction.extractor.method}
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

      <div className="tab-row" role="tablist" aria-label="文本统计视图">
        <button
          className="tab"
          type="button"
          role="tab"
          aria-selected={tab === 'long'}
          onClick={() => setTab('long')}
        >
          长表
        </button>
        <button
          className="tab"
          type="button"
          role="tab"
          aria-selected={tab === 'wide'}
          onClick={() => setTab('wide')}
        >
          宽表
        </button>
      </div>

      {tab === 'long' ? (
        <div>
          <div className="table-wrap">
            <table className="preview-table editable-table">
              <thead>
                <tr>
                  <th>导入</th>
                  <th>主体</th>
                  <th>指标</th>
                  <th>数值</th>
                  <th>单位</th>
                  <th>备注</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {facts.map((fact, index) => (
                  <tr key={`${fact.fact_id ?? 'row'}-${index}`}>
                    <td>
                      <input
                        aria-label={`导入-${index}`}
                        type="checkbox"
                        checked={fact.include !== false}
                        onChange={(event) =>
                          updateFact(index, { include: event.target.checked })
                        }
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`主体-${index}`}
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
                        aria-label={`指标-${index}`}
                        value={fact.metric}
                        onChange={(event) =>
                          updateFact(index, { metric: event.target.value, edited: true })
                        }
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`数值-${index}`}
                        value={cellText(valueOf(fact))}
                        onChange={(event) => updateNumber(index, event.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`单位-${index}`}
                        value={fact.unit ?? ''}
                        onChange={(event) =>
                          updateFact(index, { unit: event.target.value, edited: true })
                        }
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`备注-${index}`}
                        value={fact.note ?? ''}
                        onChange={(event) =>
                          updateFact(index, { note: event.target.value, edited: true })
                        }
                      />
                    </td>
                    <td>
                      <button
                        className="button ghost small"
                        type="button"
                        aria-label={`删除-${index}`}
                        onClick={() => removeRow(index)}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="inline-form">
            <button className="button ghost" type="button" onClick={addRow}>
              新增一行
            </button>
            <button
              className="button"
              type="button"
              disabled={busy || included.length === 0}
              onClick={() => void onImport('long', included)}
            >
              导入长表
            </button>
            <button
              className="button"
              type="button"
              disabled={busy || included.length === 0}
              onClick={() => void onImport('wide', included)}
            >
              导入宽表
            </button>
          </div>
        </div>
      ) : (
        <div>
          {wide.rows.length === 0 ? (
            <p className="muted">没有可预览的事实。</p>
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
              导入宽表
            </button>
            <button
              className="button"
              type="button"
              disabled={busy || included.length === 0}
              onClick={() => void onImport('long', included)}
            >
              导入长表
            </button>
          </div>
        </div>
      )}

      {onAIEnhance ? (
        <div className="ai-consent">
          <label>
            <input
              aria-label="允许 AI 增强"
              type="checkbox"
              checked={aiConsent}
              onChange={(event) => setAiConsent(event.target.checked)}
            />
            允许 AI 增强
          </label>
          <p className="muted">
            默认关闭。确认后只会发送含数字的原文片段与标题，AI 不得新增事实或修改数值。
          </p>
          <button
            className="button"
            type="button"
            disabled={busy || !aiConsent || included.length === 0}
            onClick={() => void onAIEnhance(included)}
          >
            AI 增强
          </button>
        </div>
      ) : null}
    </section>
  )
}
