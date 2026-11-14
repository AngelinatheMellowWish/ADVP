import { useTranslation } from 'react-i18next'

import type { DatasetDetail } from '../api/projects'
import type { EgressMode, Provider } from '../api/providers'
import {
  applyEgressPolicy,
  buildDatasetContext,
  selectDefaultProvider,
} from './analysisContext'

type AiContextPreviewProps = {
  dataset: DatasetDetail
  providers: Provider[]
  onClose: () => void
}

export function AiContextPreview({ dataset, providers, onClose }: AiContextPreviewProps) {
  const { t } = useTranslation()
  const provider = selectDefaultProvider(providers)
  const mode: EgressMode = provider?.egress_mode ?? 'sample'
  const sampleRows = provider?.sample_rows ?? 3
  const context = applyEgressPolicy(
    buildDatasetContext(dataset),
    mode,
    sampleRows,
    dataset.preview,
  )
  const showsSamples = mode !== 'metadata'

  return (
    <div className="modal-backdrop">
      <div
        className="modal ai-context-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('dataPage.aiContextTitle')}
      >
        <h2>{t('dataPage.aiContextTitle')}</h2>
        <p className="muted">{t('dataPage.aiContextReadOnly')}</p>
        <p className="ai-context-policy" data-testid="ai-context-policy">
          {provider
            ? t('dataPage.aiContextPolicy', {
                provider: provider.name,
                mode: t(`dataPage.egress.${mode}`),
                rows: sampleRows,
              })
            : t('dataPage.aiContextNoProvider')}
        </p>

        <h3>{t('dataPage.aiContextMetadata')}</h3>
        <dl className="ai-context-metadata" data-testid="ai-context-metadata">
          <dt>{t('dataPage.aiContextName')}</dt>
          <dd>{dataset.name}</dd>
          <dt>{t('dataPage.aiContextRows')}</dt>
          <dd>{context.row_count}</dd>
          <dt>{t('dataPage.aiContextColumns')}</dt>
          <dd>{context.columns.length}</dd>
          <dt>{t('dataPage.aiContextSampled')}</dt>
          <dd>
            {context.sampled ? t('dataPage.yes') : t('dataPage.no')}
          </dd>
        </dl>

        <h3>{t('dataPage.aiContextSchema')}</h3>
        <div className="table-wrap">
          <table className="preview-table" data-testid="ai-context-schema">
            <thead>
              <tr>
                <th>{t('dataPage.fieldName')}</th>
                <th>{t('dataPage.fieldType')}</th>
                <th>{t('dataPage.fieldSensitive')}</th>
                <th>{t('dataPage.fieldUnique')}</th>
                <th>{t('dataPage.fieldMissing')}</th>
              </tr>
            </thead>
            <tbody>
              {context.columns.map((column) => (
                <tr key={column.name}>
                  <td>{column.name}</td>
                  <td>{column.semantic_type}</td>
                  <td>{column.sensitive ? t('dataPage.yes') : t('dataPage.no')}</td>
                  <td>{column.cardinality}</td>
                  <td>{formatRate(column.null_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3>{t('dataPage.aiContextSamples')}</h3>
        <div className="ai-context-samples" data-testid="ai-context-samples">
          {!showsSamples ? (
            <p className="muted">{t('dataPage.aiContextMetadataOnly')}</p>
          ) : (
            context.columns.map((column) => (
              <div
                className="ai-context-sample-row"
                key={column.name}
                data-testid={`ai-context-samples-${column.name}`}
              >
                <strong>{column.name}</strong>
                {column.sensitive ? (
                  <span className="muted">{t('dataPage.aiContextMasked')}</span>
                ) : column.samples.length === 0 ? (
                  <span className="muted">—</span>
                ) : (
                  <span>{column.samples.map((value) => String(value ?? '—')).join(' · ')}</span>
                )}
              </div>
            ))
          )}
        </div>

        {context.preview ? (
          <>
            <h3>{t('dataPage.aiContextPreviewRows')}</h3>
            <div className="table-wrap">
              <table className="preview-table" data-testid="ai-context-preview-rows">
                <thead>
                  <tr>
                    {context.columns.map((column) => (
                      <th key={column.name}>{column.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {context.preview.map((row, index) => (
                    <tr key={index}>
                      {context.columns.map((column) => (
                        <td key={column.name}>{String(row[column.name] ?? '')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}

        <div className="modal-actions">
          <button className="btn" type="button" onClick={onClose}>
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  )
}

function formatRate(rate: number): string {
  return `${Math.round(rate * 1000) / 10}%`
}
