import { useTranslation } from 'react-i18next'

import type { ColumnDefinition } from '../api/projects'
import { matchesGroup } from '../state/chartRoles'

export type EncodingRole = {
  role: string
  group: string
  required: boolean
}

export function EncodingSlots({
  roles,
  fields,
  columns,
  onChange,
}: {
  roles: EncodingRole[]
  fields: Record<string, string>
  columns: ColumnDefinition[]
  onChange: (role: string, value: string) => void
}) {
  const { t } = useTranslation()

  return (
    <section className="card encoding-slots" aria-label={t('chartsPage.encoding')}>
      <h2>{t('chartsPage.encoding')}</h2>
      <div className="encoding-grid">
        {roles.map((role) => {
          const options = columns.filter((column) =>
            matchesGroup(column.semantic_type, role.group),
          )
          return (
            <label
              className="encoding-slot"
              key={role.role}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault()
                const value = event.dataTransfer.getData('text/plain')
                if (value) onChange(role.role, value)
              }}
            >
              <span>
                {role.role}
                {role.required ? <span className="required-mark">*</span> : null}
                <span className="muted"> · {role.group}</span>
              </span>
              <select
                className="input"
                aria-label={`${role.role} field`}
                value={fields[role.role] ?? ''}
                onChange={(event) => onChange(role.role, event.target.value)}
              >
                <option value="">{t('chartsPage.none')}</option>
                {options.map((column) => (
                  <option key={column.name} value={column.name}>
                    {column.name}
                  </option>
                ))}
              </select>
            </label>
          )
        })}
      </div>
    </section>
  )
}
