import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { ColumnDefinition } from '../api/projects'

export function FieldPanel({
  columns,
  onSelect,
}: {
  columns: ColumnDefinition[]
  onSelect: (name: string) => void
}) {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const visible = columns.filter((column) =>
    column.name.toLowerCase().includes(search.trim().toLowerCase()),
  )

  return (
    <section className="card field-panel" aria-label={t('chartsPage.fields')}>
      <h2>{t('chartsPage.fields')}</h2>
      <input
        className="input"
        type="search"
        aria-label={t('chartsPage.searchFields')}
        placeholder={t('chartsPage.searchFields')}
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <ul className="field-list">
        {visible.map((column) => (
          <li key={column.name}>
            <button
              className="field-item"
              type="button"
              draggable
              onDragStart={(event) => {
                event.dataTransfer.setData('text/plain', column.name)
                event.dataTransfer.effectAllowed = 'copy'
              }}
              onClick={() => onSelect(column.name)}
              title={t('chartsPage.fieldHint')}
            >
              <span>{column.name}</span>
              <span className="field-type">{column.semantic_type}</span>
            </button>
          </li>
        ))}
      </ul>
      {visible.length === 0 ? <p className="muted">{t('chartsPage.noFields')}</p> : null}
    </section>
  )
}
