import type { ReactNode } from 'react'

export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="card settings-section">
      <div className="panel-title">
        <div>
          <h2>{title}</h2>
          {description ? <p className="muted">{description}</p> : null}
        </div>
      </div>
      <div className="stack-form">{children}</div>
    </section>
  )
}
