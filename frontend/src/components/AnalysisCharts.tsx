import { useTranslation } from 'react-i18next'

import type { DatasetAnalysis } from '../api/analysis'
import type { ColumnProfile, DatasetDetail } from '../api/projects'

type AnalysisChartsProps = {
  dataset: DatasetDetail
  analysis: DatasetAnalysis | null
}

type HistogramBin = {
  start: number
  end: number
  count: number
}

const BIN_COUNT = 8
const NUMERIC_TYPES = new Set(['integer', 'number'])

function numericColumns(dataset: DatasetDetail): ColumnProfile[] {
  return dataset.profile.columns.filter((column) =>
    NUMERIC_TYPES.has(column.semantic_type),
  )
}

function finiteValues(dataset: DatasetDetail, column: string): number[] {
  const values: number[] = []
  for (const row of dataset.preview) {
    const value = row[column]
    if (value === null || value === undefined || value === '' || typeof value === 'boolean') {
      continue
    }
    const numeric = typeof value === 'number' ? value : Number(value)
    if (Number.isFinite(numeric)) values.push(numeric)
  }
  return values
}

function buildHistogram(values: number[]): HistogramBin[] {
  if (values.length === 0) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (min === max) {
    return [{ start: min, end: max, count: values.length }]
  }
  const width = (max - min) / BIN_COUNT
  const bins = Array.from({ length: BIN_COUNT }, (_, index) => ({
    start: min + width * index,
    end: min + width * (index + 1),
    count: 0,
  }))
  for (const value of values) {
    const index = Math.min(BIN_COUNT - 1, Math.floor((value - min) / width))
    bins[index].count += 1
  }
  return bins
}

function correlationColor(r: number): string {
  const alpha = 0.12 + Math.min(Math.abs(r), 1) * 0.5
  return r >= 0 ? `rgba(56, 189, 248, ${alpha})` : `rgba(251, 113, 133, ${alpha})`
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

export function AnalysisCharts({ dataset, analysis }: AnalysisChartsProps) {
  const { t } = useTranslation()
  const sampled = dataset.sampled || Boolean(analysis?.sampled)
  const numeric = numericColumns(dataset)
  const previewTruncated = dataset.preview.length < dataset.row_count

  return (
    <section className="card analysis-charts" data-testid="analysis-charts">
      <div className="home-section-head">
        <h2>{t('dataPage.chartsTitle')}</h2>
        {sampled ? (
          <span className="badge" data-testid="sampled-badge">
            {t('dataPage.sampledBadge')}
          </span>
        ) : null}
      </div>

      <div className="analysis-chart-block">
        <h3>{t('dataPage.missingTitle')}</h3>
        <div className="missing-bar-list">
          {dataset.profile.columns.map((column) => {
            const rate = Math.max(0, Math.min(column.null_rate, 1))
            return (
              <div
                className="missing-bar-row"
                data-testid={`missing-bar-${column.name}`}
                data-rate={column.null_rate}
                key={column.name}
              >
                <span className="missing-bar-label">{column.name}</span>
                <span className="missing-bar-track">
                  <span
                    className="missing-bar-fill"
                    style={{ width: `${rate * 100}%` }}
                  />
                </span>
                <span className="missing-bar-value">
                  {t('dataPage.missingRate', { rate: formatNumber(rate * 100) })}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      <div className="analysis-chart-block">
        <h3>{t('dataPage.correlationTitle')}</h3>
        {analysis && analysis.correlations.length > 0 ? (
          <div className="table-wrap">
            <table
              className="preview-table correlation-table"
              data-testid="correlation-table"
            >
              <thead>
                <tr>
                  <th>{t('dataPage.correlationLeft')}</th>
                  <th>{t('dataPage.correlationRight')}</th>
                  <th>{t('dataPage.correlationCoefficient')}</th>
                  <th>{t('dataPage.correlationStrengthLabel')}</th>
                </tr>
              </thead>
              <tbody>
                {analysis.correlations.map((item) => (
                  <tr
                    data-testid="correlation-row"
                    key={`${item.left}-${item.right}`}
                    style={{ background: correlationColor(item.r) }}
                  >
                    <td>{item.left}</td>
                    <td>{item.right}</td>
                    <td>{item.r.toFixed(2)}</td>
                    <td>
                      {t(`dataPage.correlationStrength.${item.strength}`, {
                        defaultValue: item.strength,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted" data-testid="correlation-empty">
            {analysis ? t('dataPage.correlationEmpty') : t('dataPage.correlationHint')}
          </p>
        )}
      </div>

      <div className="analysis-chart-block" data-testid="distribution-histogram">
        <div className="home-section-head">
          <h3>{t('dataPage.distributionTitle')}</h3>
          <div className="chart-badges">
            {dataset.sampled ? (
              <span className="badge" data-testid="distribution-sampled">
                {t('dataPage.sampledBadge')}
              </span>
            ) : null}
            {previewTruncated ? (
              <span className="badge" data-testid="distribution-truncated">
                {t('dataPage.distributionTruncated')}
              </span>
            ) : null}
          </div>
        </div>
        {numeric.length === 0 ? (
          <p className="muted">{t('dataPage.distributionEmpty')}</p>
        ) : (
          <div className="histogram-list">
            {numeric.map((column) => {
              const values = finiteValues(dataset, column.name)
              const bins = buildHistogram(values)
              const peak = Math.max(...bins.map((bin) => bin.count), 1)
              return (
                <div
                  className="histogram-column"
                  data-column={column.name}
                  key={column.name}
                >
                  <span className="histogram-label">{column.name}</span>
                  <div className="histogram-bars">
                    {bins.map((bin, index) => (
                      <span
                        className="histogram-bar"
                        data-testid="histogram-bar"
                        key={index}
                        style={{ height: `${Math.max(4, (bin.count / peak) * 100)}%` }}
                        title={`${formatNumber(bin.start)}–${formatNumber(bin.end)}: ${bin.count}`}
                      />
                    ))}
                  </div>
                  <span className="muted histogram-range">
                    {t('dataPage.distributionRange', {
                      min: bins.length ? formatNumber(bins[0].start) : '—',
                      max: bins.length ? formatNumber(bins[bins.length - 1].end) : '—',
                      count: values.length,
                    })}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
}
