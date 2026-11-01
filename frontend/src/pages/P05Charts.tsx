import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { buildChartSelection, getChartRegistry, type ChartRegistryEntry } from '../api/charts'
import {
  errorMessage,
  fetchChartCandidates,
  getDataset,
  type ChartCandidatesResponse,
  type DatasetDetail,
} from '../api/projects'
import {
  correctChartSelection,
  createChartSelection,
  type ChartSelectionResult,
} from '../api/selections'
import { useProject } from '../app/projectContext'
import { ChartConfigPanel } from '../components/ChartConfigPanel'
import { ChartFigure } from '../components/ChartFigure'
import { ChartTabs } from '../components/ChartTabs'
import { EncodingSlots, type EncodingRole } from '../components/EncodingSlots'
import { ExportPanel } from '../components/ExportPanel'
import { FieldPanel } from '../components/FieldPanel'
import { ChartEditorProvider } from '../state/ChartEditorProvider'
import {
  useChartEditor,
  type ChartStyle,
  type ChartTab,
} from '../state/chartEditorContext'
import { matchesGroup, roleGroup } from '../state/chartRoles'

const FAMILIES = ['2d', 'map', 'network', 'stream', 'imaging'] as const
type Family = (typeof FAMILIES)[number]

type Intent = 'trend' | 'distribution' | 'comparison' | 'correlation' | 'composition' | 'timeline'
const INTENTS: Intent[] = [
  'trend',
  'distribution',
  'comparison',
  'correlation',
  'composition',
  'timeline',
]

function dataKind(dataset: DatasetDetail): string {
  return dataset.kind === 'table' || dataset.kind === 'array' ? dataset.kind : dataset.kind
}

function cleanStyle(style: ChartStyle): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(style).filter(([, value]) => value !== '' && value !== undefined),
  )
}

function roleList(chart: ChartRegistryEntry | undefined): EncodingRole[] {
  if (!chart) return []
  const roles: EncodingRole[] = Object.entries(chart.requiredTypes).map(([role, group]) => ({
    role,
    group,
    required: true,
  }))
  for (const role of chart.optional) {
    if (!roles.some((item) => item.role === role)) {
      roles.push({ role, group: roleGroup(role, chart.requiredTypes), required: false })
    }
  }
  return roles
}

export function P05Charts() {
  return (
    <ChartEditorProvider>
      <P05ChartsWorkbench />
    </ChartEditorProvider>
  )
}

function P05ChartsWorkbench() {
  const { t } = useTranslation()
  const { projectId } = useParams<{ projectId?: string }>()
  const { project } = useProject()
  const [params] = useSearchParams()
  const datasetId = params.get('dataset') ?? project?.datasets[0]?.id ?? null

  const editor = useChartEditor()
  const { activeTab, activeId, tabs, canUndo, canRedo } = editor

  const [dataset, setDataset] = useState<DatasetDetail | null>(null)
  const [registry, setRegistry] = useState<ChartRegistryEntry[]>([])
  const [candidates, setCandidates] = useState<ChartCandidatesResponse | null>(null)
  const [family, setFamily] = useState<Family>('2d')
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pickedField, setPickedField] = useState<string | null>(null)
  const [showTable, setShowTable] = useState(false)

  const [intent, setIntent] = useState<Intent | ''>('')
  const [aiResult, setAiResult] = useState<ChartSelectionResult | null>(null)
  const [aiBusy, setAiBusy] = useState(false)
  const [correction, setCorrection] = useState('')
  const [correcting, setCorrecting] = useState(false)
  const [corrected, setCorrected] = useState<ChartSelectionResult | null>(null)

  useEffect(() => {
    if (!datasetId) {
      setDataset(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    getDataset(datasetId)
      .then((value) => {
        if (!cancelled) setDataset(value)
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
  }, [datasetId])

  useEffect(() => {
    let cancelled = false
    getChartRegistry()
      .then((value) => {
        if (!cancelled) setRegistry(value.charts)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!datasetId) {
      setCandidates(null)
      return
    }
    let cancelled = false
    fetchChartCandidates(datasetId)
      .then((value) => {
        if (!cancelled) setCandidates(value)
      })
      .catch(() => {
        if (!cancelled) setCandidates(null)
      })
    return () => {
      cancelled = true
    }
  }, [datasetId])

  const availableCharts = useMemo(() => {
    if (!dataset) return []
    const kind = dataKind(dataset)
    return registry.filter((chart) => chart.dataKinds.includes(kind))
  }, [dataset, registry])

  const families = useMemo(() => {
    const present = new Set(availableCharts.map((chart) => chart.family))
    return FAMILIES.filter((item) => present.has(item))
  }, [availableCharts])

  const familyCharts = useMemo(
    () => availableCharts.filter((chart) => chart.family === family),
    [availableCharts, family],
  )

  const activeChart = availableCharts.find((chart) => chart.id === activeTab.draft.chartId)
  const roles = roleList(activeChart)

  useEffect(() => {
    if (families.length === 0) return
    if (!families.includes(family)) {
      setFamily(families[0])
      return
    }
    if (familyCharts.length === 0) return
    if (!familyCharts.some((chart) => chart.id === activeTab.draft.chartId)) {
      editor.setChart(familyCharts[0].id)
    }
  }, [families, family, familyCharts, activeTab.draft.chartId, editor])

  const activeSelectionId = corrected?.id ?? activeTab.selectionId ?? null

  function pickChart(chartId: string) {
    if (chartId === activeTab.draft.chartId) return
    const chart = availableCharts.find((item) => item.id === chartId)
    if (chart) setFamily(chart.family as Family)
    const candidate = candidates?.candidates.find((item) => item.id === chartId)
    editor.setChart(chartId, candidate?.suggested_fields)
  }

  function pickField(name: string) {
    if (!dataset) return
    const column = dataset.schema_definition.columns.find((item) => item.name === name)
    if (!column) return
    const target = roles.find(
      (role) =>
        (activeTab.draft.fields[role.role] ?? '') === '' &&
        matchesGroup(column.semantic_type, role.group),
    )
    if (target) {
      editor.updateField(target.role, name)
      setPickedField(null)
    } else {
      setPickedField(name)
    }
  }

  async function renderChart() {
    if (!dataset || !activeChart || dataset.kind !== 'table') return
    setBusy(true)
    setError(null)
    try {
      const fields = Object.fromEntries(
        Object.entries(activeTab.draft.fields).filter(([, value]) => value),
      )
      const selection = await buildChartSelection(dataset.id, {
        chart_id: activeChart.id,
        fields,
        aggregation: activeTab.draft.aggregation || null,
        style: cleanStyle(activeTab.draft.style),
        parent_selection_id: activeTab.selectionId,
        reason: t('chartsPage.manualReason'),
      })
      editor.setSelectionId(selection.id)
      setCorrected(null)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function runAiSelection() {
    if (!dataset) return
    setAiBusy(true)
    setError(null)
    try {
      const result = await createChartSelection(dataset.id, {
        intent: intent || undefined,
      })
      setAiResult(result)
      setCorrected(null)
      editor.setChart(result.selected.chart_id, result.selected.fields)
      editor.setAggregation(result.selected.aggregation ?? '')
      editor.setSelectionId(result.id)
      setFamily(result.selected.family as Family)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setAiBusy(false)
    }
  }

  async function applyCorrection() {
    if (!activeSelectionId || !correction.trim()) return
    setCorrecting(true)
    setError(null)
    try {
      const result = await correctChartSelection(activeSelectionId, correction.trim())
      setCorrected(result)
      setCorrection('')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setCorrecting(false)
    }
  }

  function useAiResult() {
    if (!aiResult) return
    setFamily(aiResult.selected.family as Family)
    editor.setChart(aiResult.selected.chart_id, aiResult.selected.fields)
    editor.setAggregation(aiResult.selected.aggregation ?? '')
    editor.setSelectionId(aiResult.id)
  }

  function tabLabel(tab: ChartTab): string {
    const chart = registry.find((item) => item.id === tab.draft.chartId)
    return chart ? chart.name.zh : tab.draft.chartId
  }

  if (!datasetId) {
    return (
      <section className="page charts-page" data-testid="page-p05">
        <h1>{t('chartsPage.title')}</h1>
        <p className="muted">{t('chartsPage.missingDataset')}</p>
        {project && project.datasets.length > 0 ? (
          <ul className="file-list">
            {project.datasets.map((item) => (
              <li key={item.id}>
                <span>{item.name}</span>
                <Link
                  className="btn"
                  to={`/projects/${projectId}/charts?dataset=${item.id}`}
                >
                  {t('chartsPage.selectDataset')}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    )
  }

  return (
    <section className="page charts-page" data-testid="page-p05">
      <header className="import-head">
        <div>
          <h1>{dataset?.name ?? t('chartsPage.title')}</h1>
          <p className="muted">
            {t('chartsPage.rows', { count: dataset?.row_count ?? 0 })} ·{' '}
            {t('chartsPage.columns', { count: dataset?.column_count ?? 0 })}
            {dataset?.sampled ? ` · ${t('chartsPage.sampled')}` : ''}
          </p>
        </div>
        <Link className="btn" to={`/projects/${projectId}/pipeline?dataset=${datasetId}`}>
          {t('chartsPage.backToPipeline')}
        </Link>
      </header>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {loading ? <p className="muted">{t('chartsPage.loading')}</p> : null}
      {dataset && dataset.kind !== 'table' ? (
        <p className="notice">{t('chartsPage.manualUnavailable')}</p>
      ) : null}

      <ChartTabs
        tabs={tabs}
        activeId={activeId}
        labelFor={tabLabel}
        onSelect={editor.selectTab}
        onAdd={editor.addTab}
        onClose={editor.closeTab}
      />

      <div className="chart-toolbar">
        <label>
          {t('chartsPage.family')}
          <select
            className="input"
            value={family}
            onChange={(event) => setFamily(event.target.value as Family)}
          >
            {(families.length > 0 ? families : FAMILIES).map((item) => (
              <option key={item} value={item}>
                {t(`chartsPage.families.${item}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('chartsPage.chartType')}
          <select
            className="input"
            aria-label={t('chartsPage.chartType')}
            value={activeTab.draft.chartId}
            onChange={(event) => pickChart(event.target.value)}
          >
            {familyCharts.map((chart) => (
              <option key={chart.id} value={chart.id}>
                {chart.name.zh} · {chart.id}
              </option>
            ))}
          </select>
        </label>
        <div className="chart-toolbar-actions">
          <button
            className="btn"
            type="button"
            onClick={editor.undo}
            disabled={!canUndo}
          >
            {t('chartsPage.undo')}
          </button>
          <button
            className="btn"
            type="button"
            onClick={editor.redo}
            disabled={!canRedo}
          >
            {t('chartsPage.redo')}
          </button>
          <button className="btn" type="button" onClick={editor.reset}>
            {t('chartsPage.reset')}
          </button>
          <button
            className="btn"
            type="button"
            onClick={() => setShowTable((value) => !value)}
          >
            {showTable ? t('chartsPage.hideTable') : t('chartsPage.showTable')}
          </button>
          <button
            className="btn home-primary"
            type="button"
            onClick={() => void renderChart()}
            disabled={busy || dataset?.kind !== 'table' || !activeChart}
          >
            {busy ? t('chartsPage.rendering') : t('chartsPage.render')}
          </button>
        </div>
      </div>

      {pickedField ? (
        <p className="notice">
          {t('chartsPage.pickedField', {
            name: pickedField,
            roles: roles.map((role) => role.role).join(', '),
          })}
        </p>
      ) : null}

      <div className="chart-workbench">
        <FieldPanel
          columns={dataset?.schema_definition.columns ?? []}
          onSelect={pickField}
        />

        <div className="chart-center">
          <EncodingSlots
            roles={roles}
            fields={activeTab.draft.fields}
            columns={dataset?.schema_definition.columns ?? []}
            onChange={editor.updateField}
          />

          <section className="card chart-canvas" aria-label={t('chartsPage.canvas')}>
            <div className="chart-canvas-head">
              <h2>{t('chartsPage.canvas')}</h2>
              {activeSelectionId ? (
                <span className="muted">{t('chartsPage.selection', { id: activeSelectionId })}</span>
              ) : (
                <span className="muted">{t('chartsPage.noChart')}</span>
              )}
            </div>
            {activeSelectionId ? (
              <div data-testid="chart-figure">
                <ChartFigure selectionId={activeSelectionId} />
              </div>
            ) : (
              <p className="muted">{t('chartsPage.canvasEmpty')}</p>
            )}
            {showTable && dataset ? (
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
            ) : null}
          </section>
        </div>

        <div className="chart-side">
          <ChartConfigPanel
            draft={activeTab.draft}
            onAggregation={editor.setAggregation}
            onStyle={editor.updateStyle}
          />

          <section className="card" aria-label={t('chartsPage.aiSelection')}>
            <h2>{t('chartsPage.aiSelection')}</h2>
            <label>
              {t('chartsPage.intent')}
              <select
                className="input"
                value={intent}
                onChange={(event) => setIntent(event.target.value as Intent | '')}
              >
                <option value="">{t('chartsPage.auto')}</option>
                {INTENTS.map((value) => (
                  <option key={value} value={value}>
                    {t(`pipelinePage.intents.${value}`)}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="btn"
              type="button"
              onClick={() => void runAiSelection()}
              disabled={aiBusy || !dataset}
            >
              {aiBusy ? t('chartsPage.aiRunning') : t('chartsPage.runAi')}
            </button>
            {aiResult ? (
              <div className="chart-ai-result" data-testid="chart-ai-result">
                <p>
                  <strong>{aiResult.selected.name.zh}</strong> ·{' '}
                  {aiResult.selected.score.toFixed(3)}
                </p>
                {aiResult.degraded ? (
                  <p className="notice">
                    {t('pipelinePage.degraded')}: {aiResult.degradation_reason ?? '—'}
                  </p>
                ) : null}
                <ol className="top3-list" data-testid="chart-top3">
                  {aiResult.top3.map((entry) => (
                    <li key={entry.chart_id} className={entry.selected ? 'selected' : ''}>
                      <strong>{entry.name.zh}</strong>
                      <span className="muted"> · {entry.score.toFixed(3)}</span>
                      <p className="muted">{entry.reason}</p>
                    </li>
                  ))}
                </ol>
                <button className="btn" type="button" onClick={useAiResult}>
                  {t('chartsPage.useAiChart')}
                </button>
              </div>
            ) : null}
            <div className="inline-form chart-correction">
              <input
                className="input"
                aria-label={t('chartsPage.correction')}
                placeholder={t('chartsPage.correctionPlaceholder')}
                value={correction}
                onChange={(event) => setCorrection(event.target.value)}
              />
              <button
                className="btn"
                type="button"
                onClick={() => void applyCorrection()}
                disabled={correcting || !correction.trim() || !activeSelectionId}
              >
                {correcting ? t('chartsPage.correcting') : t('chartsPage.applyCorrection')}
              </button>
            </div>
          </section>

          {activeSelectionId ? (
            <section className="card" aria-label={t('chartsPage.export')}>
              <h2>{t('chartsPage.export')}</h2>
              <ExportPanel selectionId={activeSelectionId} />
            </section>
          ) : null}
        </div>
      </div>
    </section>
  )
}
