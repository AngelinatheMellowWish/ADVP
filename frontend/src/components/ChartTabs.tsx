import { useTranslation } from 'react-i18next'

import type { ChartTab } from '../state/chartEditorContext'

export function ChartTabs({
  tabs,
  activeId,
  labelFor,
  onSelect,
  onAdd,
  onClose,
}: {
  tabs: ChartTab[]
  activeId: string
  labelFor: (tab: ChartTab) => string
  onSelect: (id: string) => void
  onAdd: () => void
  onClose: (id: string) => void
}) {
  const { t } = useTranslation()

  return (
    <div className="chart-tabs" role="tablist" aria-label={t('chartsPage.tabs')}>
      {tabs.map((tab) => (
        <div className="chart-tab-wrap" key={tab.id}>
          <button
            className={tab.id === activeId ? 'chart-tab active' : 'chart-tab'}
            type="button"
            role="tab"
            aria-selected={tab.id === activeId}
            onClick={() => onSelect(tab.id)}
          >
            {labelFor(tab)}
          </button>
          {tabs.length > 1 ? (
            <button
              className="chart-tab-close"
              type="button"
              aria-label={`${t('common.close')} ${labelFor(tab)}`}
              onClick={() => onClose(tab.id)}
            >
              ×
            </button>
          ) : null}
        </div>
      ))}
      <button className="chart-tab-add" type="button" onClick={onAdd}>
        + {t('chartsPage.addTab')}
      </button>
    </div>
  )
}
