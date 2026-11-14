import { useTranslation } from 'react-i18next'

import {
  MAX_SAMPLE_ROWS,
  hasInvalidTypeOverrides,
  type AdvancedFileOptionsValue,
} from './advancedFileOptionsConfig'

const ENCODINGS = ['UTF-8', 'GBK', 'Latin-1'] as const
const DELIMITERS = [
  { value: ',', key: 'comma' },
  { value: '\t', key: 'tab' },
  { value: ';', key: 'semicolon' },
  { value: '|', key: 'pipe' },
] as const

type Props = {
  values: AdvancedFileOptionsValue
  onChange: (values: AdvancedFileOptionsValue) => void
  onReset: () => void
}

export function AdvancedFileOptions({ values, onChange, onReset }: Props) {
  const { t } = useTranslation()
  const delimiterInvalid = values.delimiter.length > 1
  const sampleRowsInvalid =
    !Number.isInteger(values.sampleRows) ||
    values.sampleRows < 1 ||
    values.sampleRows > MAX_SAMPLE_ROWS
  const typeOverridesInvalid = hasInvalidTypeOverrides(values.typeOverrides)

  function update<K extends keyof AdvancedFileOptionsValue>(
    key: K,
    value: AdvancedFileOptionsValue[K],
  ) {
    onChange({ ...values, [key]: value })
  }

  return (
    <details className="advanced-file-options">
      <summary>{t('importPage.file.advanced.toggle')}</summary>
      <p className="muted">{t('importPage.file.advanced.description')}</p>

      <div className="advanced-file-grid">
        <div className="field">
          <label htmlFor="advanced-encoding">{t('importPage.file.advanced.encoding')}</label>
          <select
            id="advanced-encoding"
            className="input"
            value={values.encoding}
            onChange={(event) => update('encoding', event.target.value)}
          >
            <option value="">{t('importPage.file.advanced.auto')}</option>
            {ENCODINGS.map((encoding) => (
              <option key={encoding} value={encoding}>
                {encoding}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="advanced-delimiter">{t('importPage.file.advanced.delimiter')}</label>
          <select
            id="advanced-delimiter"
            className="input"
            value={values.delimiter}
            aria-invalid={delimiterInvalid}
            onChange={(event) => update('delimiter', event.target.value)}
          >
            <option value="">{t('importPage.file.advanced.auto')}</option>
            {DELIMITERS.map((delimiter) => (
              <option key={delimiter.key} value={delimiter.value}>
                {t(`importPage.file.advanced.delimiters.${delimiter.key}`)}
              </option>
            ))}
          </select>
          {delimiterInvalid ? (
            <p className="hint error-text">{t('importPage.file.advanced.delimiterHint')}</p>
          ) : null}
        </div>

        <div className="field">
          <label htmlFor="advanced-sample-rows">{t('importPage.file.advanced.sampleRows')}</label>
          <input
            id="advanced-sample-rows"
            className="input"
            type="number"
            min={1}
            max={MAX_SAMPLE_ROWS}
            value={values.sampleRows}
            aria-invalid={sampleRowsInvalid}
            onChange={(event) => update('sampleRows', Number(event.target.value))}
          />
          {sampleRowsInvalid ? (
            <p className="hint error-text">{t('importPage.file.advanced.sampleRowsHint')}</p>
          ) : null}
        </div>

        <div className="field">
          <label htmlFor="advanced-sheet-variable">
            {t('importPage.file.advanced.sheetOrVariable')}
          </label>
          <input
            id="advanced-sheet-variable"
            className="input"
            value={values.sheetOrVariable}
            onChange={(event) => update('sheetOrVariable', event.target.value)}
          />
          <p className="hint">{t('importPage.file.advanced.sheetOrVariableHint')}</p>
        </div>

        <div className="field full">
          <label htmlFor="advanced-missing-markers">
            {t('importPage.file.advanced.missingMarkers')}
          </label>
          <input
            id="advanced-missing-markers"
            className="input"
            value={values.missingMarkers}
            onChange={(event) => update('missingMarkers', event.target.value)}
          />
          <p className="hint">{t('importPage.file.advanced.missingMarkersHint')}</p>
        </div>

        <div className="field full">
          <label htmlFor="advanced-type-overrides">
            {t('importPage.file.advanced.typeOverrides')}
          </label>
          <input
            id="advanced-type-overrides"
            className="input"
            value={values.typeOverrides}
            aria-invalid={typeOverridesInvalid}
            onChange={(event) => update('typeOverrides', event.target.value)}
          />
          <p className={typeOverridesInvalid ? 'hint error-text' : 'hint'}>
            {t('importPage.file.advanced.typeOverridesHint')}
          </p>
        </div>
      </div>

      <label className="checkbox-field">
        <input
          type="checkbox"
          checked={values.hasHeader}
          onChange={(event) => update('hasHeader', event.target.checked)}
        />
        {t('importPage.file.advanced.header')}
      </label>

      <div className="import-actions">
        <button className="btn" type="button" onClick={onReset}>
          {t('importPage.file.advanced.reset')}
        </button>
      </div>
    </details>
  )
}
