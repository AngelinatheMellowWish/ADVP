import { useTranslation } from 'react-i18next'

import type { ReportCustomSection } from '../api/pipelines'

type ReportCustomSectionsProps = {
  value: ReportCustomSection[]
  onChange: (value: ReportCustomSection[]) => void
  disabled?: boolean
}

export function ReportCustomSections({
  value,
  onChange,
  disabled = false,
}: ReportCustomSectionsProps) {
  const { t } = useTranslation()

  function update(index: number, patch: Partial<ReportCustomSection>) {
    onChange(
      value.map((section, current) =>
        current === index ? { ...section, ...patch } : section,
      ),
    )
  }

  function move(index: number, delta: number) {
    const target = index + delta
    if (target < 0 || target >= value.length) return
    const next = [...value]
    const [item] = next.splice(index, 1)
    next.splice(target, 0, item)
    onChange(next.map((section, position) => ({ ...section, position })))
  }

  function add() {
    onChange([
      ...value,
      {
        key: `custom-${Date.now()}`,
        title: t('reportPage.customSections.defaultTitle'),
        body: '',
        position: value.length,
        include_charts: false,
      },
    ])
  }

  return (
    <section className="report-custom-sections" data-testid="report-custom-sections">
      <div className="panel-title">
        <h3>{t('reportPage.customSections.title')}</h3>
        <button
          className="btn"
          type="button"
          data-testid="add-custom-section"
          onClick={add}
          disabled={disabled}
        >
          {t('reportPage.customSections.add')}
        </button>
      </div>
      {value.length === 0 ? (
        <p className="muted">{t('reportPage.customSections.empty')}</p>
      ) : (
        <ol className="custom-section-list">
          {value.map((section, index) => (
            <li key={section.key} data-testid={`custom-section-${section.key}`}>
              <input
                className="input"
                data-testid={`custom-section-title-${index}`}
                aria-label={t('reportPage.customSections.sectionTitle')}
                value={section.title}
                disabled={disabled}
                onChange={(event) => update(index, { title: event.target.value })}
              />
              <textarea
                className="input"
                rows={3}
                data-testid={`custom-section-body-${index}`}
                aria-label={t('reportPage.customSections.sectionBody')}
                value={section.body}
                disabled={disabled}
                onChange={(event) => update(index, { body: event.target.value })}
              />
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={section.include_charts}
                  disabled={disabled}
                  onChange={(event) =>
                    update(index, { include_charts: event.target.checked })
                  }
                />
                {t('reportPage.customSections.includeCharts')}
              </label>
              <div className="inline-form">
                <button
                  className="btn"
                  type="button"
                  onClick={() => move(index, -1)}
                  disabled={disabled || index === 0}
                >
                  {t('reportPage.customSections.up')}
                </button>
                <button
                  className="btn"
                  type="button"
                  onClick={() => move(index, 1)}
                  disabled={disabled || index === value.length - 1}
                >
                  {t('reportPage.customSections.down')}
                </button>
                <button
                  className="btn"
                  type="button"
                  onClick={() =>
                    onChange(
                      value
                        .filter((_, current) => current !== index)
                        .map((item, position) => ({ ...item, position })),
                    )
                  }
                  disabled={disabled}
                >
                  {t('reportPage.customSections.remove')}
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
