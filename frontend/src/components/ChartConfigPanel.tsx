import { useTranslation } from 'react-i18next'

import type { ChartDraft, ChartStyle } from '../state/chartEditorContext'

const AGGREGATIONS = ['sum', 'mean', 'median', 'min', 'max', 'count']
const LEGEND_POSITIONS = ['right', 'bottom', 'top', 'left']

export function ChartConfigPanel({
  draft,
  onAggregation,
  onStyle,
}: {
  draft: ChartDraft
  onAggregation: (value: string) => void
  onStyle: (patch: Partial<ChartStyle>) => void
}) {
  const { t } = useTranslation()

  return (
    <section className="card chart-config" aria-label={t('chartsPage.config')}>
      <h2>{t('chartsPage.config')}</h2>
      <label>
        {t('chartsPage.aggregation')}
        <select
          className="input"
          value={draft.aggregation}
          onChange={(event) => onAggregation(event.target.value)}
        >
          <option value="">{t('chartsPage.none')}</option>
          {AGGREGATIONS.map((value) => (
            <option key={value} value={value}>
              {t(`chartsPage.aggregations.${value}`)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('chartsPage.chartTitle')}
        <input
          className="input"
          value={draft.style.title ?? ''}
          onChange={(event) => onStyle({ title: event.target.value })}
        />
      </label>
      <label>
        {t('chartsPage.color')}
        <input
          className="input"
          placeholder="#35d0ba"
          value={draft.style.color ?? ''}
          onChange={(event) => onStyle({ color: event.target.value })}
        />
      </label>
      <label>
        {t('chartsPage.legend')}
        <select
          className="input"
          value={draft.style.legend_position ?? ''}
          onChange={(event) => onStyle({ legend_position: event.target.value })}
        >
          <option value="">{t('chartsPage.none')}</option>
          {LEGEND_POSITIONS.map((value) => (
            <option key={value} value={value}>
              {t(`chartsPage.legendPositions.${value}`)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t('chartsPage.barMode')}
        <select
          className="input"
          value={draft.style.barmode ?? ''}
          onChange={(event) => onStyle({ barmode: event.target.value })}
        >
          <option value="">{t('chartsPage.none')}</option>
          <option value="group">{t('chartsPage.barModes.group')}</option>
          <option value="stack">{t('chartsPage.barModes.stack')}</option>
          <option value="overlay">{t('chartsPage.barModes.overlay')}</option>
        </select>
      </label>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.style.log_x === true}
          onChange={(event) => onStyle({ log_x: event.target.checked })}
        />
        {t('chartsPage.logX')}
      </label>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.style.log_y === true}
          onChange={(event) => onStyle({ log_y: event.target.checked })}
        />
        {t('chartsPage.logY')}
      </label>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.style.dual_y === true}
          onChange={(event) => onStyle({ dual_y: event.target.checked })}
        />
        {t('chartsPage.dualY')}
      </label>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={draft.style.colorblind_palette === true}
          onChange={(event) => onStyle({ colorblind_palette: event.target.checked })}
        />
        {t('chartsPage.colorblind')}
      </label>
    </section>
  )
}
