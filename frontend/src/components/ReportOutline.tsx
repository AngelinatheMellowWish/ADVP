import { useTranslation } from 'react-i18next'

import type { ReportSection } from '../api/pipelines'

type Props = {
  value: ReportSection[]
  onChange: (next: ReportSection[]) => void
  disabled?: boolean
}

export function ReportOutline({ value, onChange, disabled = false }: Props) {
  const { t } = useTranslation()

  function move(index: number, direction: -1 | 1) {
    const target = index + direction
    if (target < 0 || target >= value.length) return
    const next = [...value]
    const [item] = next.splice(index, 1)
    next.splice(target, 0, item)
    onChange(next)
  }

  function drop(index: number, dragged: string) {
    const from = value.indexOf(dragged as ReportSection)
    if (from < 0 || from === index) return
    const next = [...value]
    const [item] = next.splice(from, 1)
    next.splice(index, 0, item)
    onChange(next)
  }

  return (
    <ol className="report-outline" data-testid="report-outline">
      {value.map((section, index) => {
        const label = t(`reportPage.sections.${section}`)
        return (
          <li
            key={section}
            draggable={!disabled}
            onDragStart={(event) => event.dataTransfer.setData('text/plain', section)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
              drop(index, event.dataTransfer.getData('text/plain'))
            }}
          >
            <span className="report-outline-label">{label}</span>
            <span className="inline-form">
              <button
                type="button"
                className="btn"
                onClick={() => move(index, -1)}
                disabled={disabled || index === 0}
              >
                {t('reportPage.moveUp', { section: label })}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => move(index, 1)}
                disabled={disabled || index === value.length - 1}
              >
                {t('reportPage.moveDown', { section: label })}
              </button>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
