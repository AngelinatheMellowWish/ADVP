import { NavLink, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

type NavEntry = {
  id: string
  labelKey: string
  path?: string
  to?: string
  end?: boolean
}

const WORKFLOW_ENTRIES: NavEntry[] = [
  { id: 'p01', labelKey: 'nav.home', to: '/', end: true },
  { id: 'p02', labelKey: 'nav.import', path: 'import' },
  { id: 'p03', labelKey: 'nav.data', path: 'data' },
  { id: 'p04', labelKey: 'nav.pipeline', path: 'pipeline' },
  { id: 'p05', labelKey: 'nav.charts', path: 'charts' },
  { id: 'p06', labelKey: 'nav.scene', path: 'scene' },
  { id: 'p07', labelKey: 'nav.reports', path: 'reports' },
  { id: 'p09', labelKey: 'nav.trace', path: 'trace' },
]

const TOOL_ENTRIES: NavEntry[] = [
  { id: 'p08', labelKey: 'nav.providers', to: '/settings/providers', end: true },
  { id: 'p10', labelKey: 'nav.settings', to: '/settings', end: true },
]

function navClassName({ isActive }: { isActive: boolean }) {
  return isActive ? 'list-button active' : 'list-button'
}

export function Sidebar() {
  const { t } = useTranslation()
  const { projectId } = useParams<{ projectId?: string }>()

  function renderEntry(entry: NavEntry) {
    const label = t(entry.labelKey)

    if (entry.path) {
      if (!projectId) {
        return (
          <li key={entry.id}>
            <span
              className="list-button nav-disabled"
              role="link"
              aria-disabled="true"
              aria-label={`${label}. ${t('topbar.selectProject')}`}
              tabIndex={0}
              title={t('topbar.selectProject')}
            >
              {label}
            </span>
          </li>
        )
      }
      return (
        <li key={entry.id}>
          <NavLink
            to={`/projects/${encodeURIComponent(projectId)}/${entry.path}`}
            end
            className={navClassName}
          >
            {label}
          </NavLink>
        </li>
      )
    }

    return (
      <li key={entry.id}>
        <NavLink to={entry.to ?? '/'} end={entry.end} className={navClassName}>
          {label}
        </NavLink>
      </li>
    )
  }

  return (
    <aside className="sidebar">
      <div className="brand" aria-label="ADVP" data-testid="app-brand">
        ADVP
      </div>
      <nav aria-label={t('nav.primary')}>
        <section aria-labelledby="nav-workflow">
          <h2 id="nav-workflow" className="muted">
            {t('nav.workflow')}
          </h2>
          <ul className="project-list">{WORKFLOW_ENTRIES.map(renderEntry)}</ul>
        </section>
        <section aria-labelledby="nav-tools">
          <h2 id="nav-tools" className="muted">
            {t('nav.tools')}
          </h2>
          <ul className="project-list">{TOOL_ENTRIES.map(renderEntry)}</ul>
        </section>
      </nav>
    </aside>
  )
}
