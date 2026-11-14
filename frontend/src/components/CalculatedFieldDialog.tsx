import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  createCalculatedField,
  errorMessage,
  previewCalculatedField,
  removeCalculatedField,
  type CalculatedFieldPreview,
  type CalculatedFieldRemoveResult,
  type CalculatedFieldResult,
  type ColumnDefinition,
} from '../api/projects'

type CalculatedFieldDialogProps = {
  datasetId: string
  columns: ColumnDefinition[]
  onApplied: (result: CalculatedFieldResult) => void
  onUndone: (result: CalculatedFieldRemoveResult) => void
  onClose: () => void
}

export function CalculatedFieldDialog({
  datasetId,
  columns,
  onApplied,
  onUndone,
  onClose,
}: CalculatedFieldDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [expression, setExpression] = useState('')
  const [preview, setPreview] = useState<CalculatedFieldPreview | null>(null)
  const [result, setResult] = useState<CalculatedFieldResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const outputColumn = name.trim() || 'calculated'
  const canSubmit = expression.trim().length > 0 && name.trim().length > 0 && !busy

  const previewValue = useMemo(() => {
    if (!preview) return null
    return preview.preview[0]?.[preview.output_column]
  }, [preview])

  async function handlePreview() {
    if (!expression.trim()) return
    setBusy(true)
    setError(null)
    try {
      const value = await previewCalculatedField(
        datasetId,
        expression.trim(),
        outputColumn,
      )
      setPreview(value)
    } catch (caught) {
      setPreview(null)
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleApply() {
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    try {
      const value = await createCalculatedField(datasetId, {
        name: name.trim(),
        expression: expression.trim(),
        output_column: outputColumn,
      })
      setResult(value)
      setPreview(null)
      onApplied(value)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleUndo() {
    if (!result) return
    setBusy(true)
    setError(null)
    try {
      const value = await removeCalculatedField(
        result.source_dataset_id,
        result.dataset.id,
      )
      setResult(null)
      onUndone(value)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop">
      <div
        className="modal calculated-field-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('chartsPage.calculatedField.title')}
      >
        <h2>{t('chartsPage.calculatedField.title')}</h2>
        <p className="muted">{t('chartsPage.calculatedField.description')}</p>

        {error ? (
          <p className="error-text" role="alert">
            {error}
          </p>
        ) : null}

        <label>
          {t('chartsPage.calculatedField.name')}
          <input
            className="input"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t('chartsPage.calculatedField.namePlaceholder')}
          />
        </label>

        <label>
          {t('chartsPage.calculatedField.expression')}
          <input
            className="input"
            list="calculated-field-columns"
            value={expression}
            onChange={(event) => setExpression(event.target.value)}
            placeholder={t('chartsPage.calculatedField.expressionPlaceholder')}
          />
        </label>
        <datalist id="calculated-field-columns" data-testid="calculated-column-options">
          {columns.map((column) => (
            <option key={column.name} value={column.name}>
              {column.name}
            </option>
          ))}
        </datalist>
        <p className="muted">
          {t('chartsPage.calculatedField.functionHint')}
        </p>

        <div className="modal-actions">
          <button
            className="btn"
            type="button"
            onClick={() => void handlePreview()}
            disabled={busy || !expression.trim()}
          >
            {busy ? t('chartsPage.calculatedField.previewing') : t('chartsPage.calculatedField.preview')}
          </button>
          <button
            className="btn home-primary"
            type="button"
            onClick={() => void handleApply()}
            disabled={!canSubmit}
          >
            {busy ? t('chartsPage.calculatedField.applying') : t('chartsPage.calculatedField.apply')}
          </button>
        </div>

        {preview ? (
          <div className="calculated-preview" data-testid="calculated-preview">
            <p>
              <strong>{t('chartsPage.calculatedField.outputType')}</strong>:{' '}
              {preview.output_type}
            </p>
            <p>
              <strong>{t('chartsPage.calculatedField.expression')}</strong>:{' '}
              {preview.expression}
            </p>
            <p className="muted">
              {t('chartsPage.calculatedField.previewRow', {
                column: preview.output_column,
                value: String(previewValue ?? ''),
              })}
            </p>
          </div>
        ) : null}

        {result ? (
          <div className="calculated-result" data-testid="calculated-result">
            <p>
              {t('chartsPage.calculatedField.applied', {
                column: result.output_column,
                type: result.output_type,
              })}
            </p>
            <p className="muted">
              {t('chartsPage.calculatedField.lineage', {
                source: result.source_dataset_id,
              })}
            </p>
            <button
              className="btn"
              type="button"
              onClick={() => void handleUndo()}
              disabled={busy}
            >
              {t('chartsPage.calculatedField.undo')}
            </button>
          </div>
        ) : null}

        <div className="modal-actions">
          <button className="btn" type="button" onClick={onClose}>
            {t('chartsPage.calculatedField.close')}
          </button>
        </div>
      </div>
    </div>
  )
}
