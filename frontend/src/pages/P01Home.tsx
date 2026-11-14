import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import {
  createProject,
  errorMessage,
  listProjects,
  request,
  type ProjectSummary,
} from '../api/projects'
import { getSystemStatus, type SystemStatus } from '../api/system'
import { ProjectCard } from '../components/ProjectCard'
import { SystemStatusCard } from '../components/SystemStatusCard'

type AuditEventItem = {
  id: string
  project_id?: string | null
  event: string
  target_type?: string | null
  target_id?: string | null
  detail?: unknown
  created_at: string
}

type ActivityFilter = 'all' | 'tasks' | 'activity'

type ActivityEntry = {
  id: string
  kind: 'task' | 'activity'
  title: string
  detail: string | null
  status: string
  createdAt: string
}

const TASK_KIND_KEYS: Record<string, string> = {
  import: 'home.recentActivity.taskKinds.import',
  pipeline: 'home.recentActivity.taskKinds.pipeline',
  export: 'home.recentActivity.taskKinds.export',
  render: 'home.recentActivity.taskKinds.render',
  live: 'home.recentActivity.taskKinds.live',
}

const ACTIVITY_FILTERS: ActivityFilter[] = ['all', 'tasks', 'activity']

function timestampOf(value: string): number {
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

function humanize(value: string): string {
  const words = value.replace(/[_-]+/g, ' ').trim()
  return words ? `${words.charAt(0).toUpperCase()}${words.slice(1)}` : value
}

function activityStatus(event: string): string {
  if (/failed|error/.test(event)) return 'failed'
  if (/cancel/.test(event)) return 'cancelled'
  if (/skip/.test(event)) return 'skipped'
  if (/pause|degrad/.test(event)) return 'paused'
  return 'recorded'
}

function statusTone(status: string): string {
  if (status === 'succeeded' || status === 'running') return 'ok'
  if (status === 'failed' || status === 'error') return 'error'
  if (status === 'pending' || status === 'paused') return 'warning'
  return 'muted'
}

function formatActivityTime(value: string, language: string): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat(language, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function P01Home() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [projectsError, setProjectsError] = useState<string | null>(null)
  const [projectsReload, setProjectsReload] = useState(0)
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(true)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [statusReload, setStatusReload] = useState(0)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([])
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>('all')
  const [activityDialogOpen, setActivityDialogOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setProjectsLoading(true)
    setProjectsError(null)
    listProjects()
      .then((data) => {
        if (cancelled) return
        setProjects(Array.isArray(data) ? data : [])
        setProjectsError(null)
      })
      .catch((caught: unknown) => {
        if (cancelled) return
        setProjects([])
        setProjectsError(errorMessage(caught))
      })
      .finally(() => {
        if (!cancelled) setProjectsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [projectsReload])

  useEffect(() => {
    const controller = new AbortController()
    setStatusLoading(true)
    setStatusError(null)
    getSystemStatus(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setStatus(data)
        setStatusError(null)
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        setStatus(null)
        setStatusError(errorMessage(caught))
      })
      .finally(() => {
        if (!controller.signal.aborted) setStatusLoading(false)
      })
    return () => controller.abort()
  }, [statusReload])

  useEffect(() => {
    let cancelled = false
    request<AuditEventItem[]>('/api/audit/events?limit=20')
      .then((data) => {
        if (cancelled) return
        setAuditEvents(Array.isArray(data) ? data : [])
      })
      .catch(() => {
        if (!cancelled) setAuditEvents([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  const activeProject = useMemo(() => {
    const candidates = projects
      .filter((project) => !project.archived)
      .sort((left, right) => timestampOf(right.updated_at) - timestampOf(left.updated_at))
    return candidates[0] ?? null
  }, [projects])

  const recentActivity = useMemo(() => {
    const entries: ActivityEntry[] = []
    const tasks = status?.recent_tasks ?? {}
    Object.entries(tasks).forEach(([, items]) => {
      if (!Array.isArray(items)) return
      items.forEach((item) => {
        if (!item || typeof item !== 'object') return
        const kind = String(item.kind ?? '')
        const titleKey = TASK_KIND_KEYS[kind]
        entries.push({
          id: `task-${item.id}`,
          kind: 'task',
          title: titleKey ? t(titleKey) : humanize(kind || 'task'),
          detail: item.id ? `#${String(item.id).slice(0, 8)}` : null,
          status: String(item.status ?? 'pending'),
          createdAt: String(item.created_at ?? ''),
        })
      })
    })
    auditEvents.forEach((event) => {
      entries.push({
        id: `activity-${event.id}`,
        kind: 'activity',
        title: t(`home.recentActivity.events.${event.event}`, {
          defaultValue: humanize(event.event),
        }),
        detail: event.target_type
          ? t(`home.recentActivity.targets.${event.target_type}`, {
              defaultValue: humanize(event.target_type),
            })
          : null,
        status: activityStatus(event.event),
        createdAt: event.created_at,
      })
    })
    return entries.sort(
      (left, right) => timestampOf(right.createdAt) - timestampOf(left.createdAt),
    )
  }, [auditEvents, status, t])

  const filteredActivity = useMemo(() => {
    if (activityFilter === 'all') return recentActivity
    const targetKind = activityFilter === 'tasks' ? 'task' : 'activity'
    return recentActivity.filter((entry) => entry.kind === targetKind)
  }, [activityFilter, recentActivity])

  const previewActivity = filteredActivity.slice(0, 4)

  function refreshProjects() {
    setProjectsReload((value) => value + 1)
  }

  function refreshStatus() {
    setStatusReload((value) => value + 1)
  }

  function openImport() {
    if (!activeProject) {
      openNewProject()
      return
    }
    navigate(`/projects/${encodeURIComponent(activeProject.id)}/import`)
  }

  function openNewProject() {
    setNewName('')
    setCreateError(null)
    setDialogOpen(true)
  }

  function closeNewProject() {
    if (creating) return
    setDialogOpen(false)
  }

  function closeActivityDialog() {
    setActivityDialogOpen(false)
  }

  function handleActivityDialogKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.stopPropagation()
      closeActivityDialog()
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = newName.trim()
    if (!trimmed) {
      setCreateError(t('home.newProject.nameRequired'))
      return
    }
    setCreating(true)
    setCreateError(null)
    try {
      const project = await createProject(trimmed)
      setDialogOpen(false)
      navigate(`/projects/${encodeURIComponent(project.id)}/import`)
    } catch (caught) {
      setCreateError(`${t('home.newProject.error')} ${errorMessage(caught)}`)
    } finally {
      setCreating(false)
    }
  }

  function handleDialogKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.stopPropagation()
      closeNewProject()
    }
  }

  function renderActivityList(entries: ActivityEntry[], testId: string) {
    if (entries.length === 0) {
      return (
        <p className="muted">
          {recentActivity.length === 0
            ? t('home.recentActivity.empty')
            : t('home.recentActivity.emptyFiltered')}
        </p>
      )
    }
    return (
      <ul className="home-activity-list" data-testid={testId}>
        {entries.map((entry) => {
          const time = formatActivityTime(entry.createdAt, i18n.language)
          return (
            <li className="home-activity-item" key={entry.id}>
              <div className="home-activity-main">
                <span className="home-activity-title">{entry.title}</span>
                {entry.detail ? (
                  <span className="home-hint">{entry.detail}</span>
                ) : null}
                {time ? (
                  <time className="home-hint" dateTime={entry.createdAt}>
                    {time}
                  </time>
                ) : null}
              </div>
              <span
                className={`status-pill status-pill-${statusTone(entry.status)}`}
                data-status={entry.status}
              >
                {t(`home.recentActivity.statuses.${entry.status}`, {
                  defaultValue: humanize(entry.status),
                })}
              </span>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <section className="home-page" data-testid="page-p01">
      <header className="home-hero">
        <div className="home-hero-copy">
          <p className="home-eyebrow">{t('home.eyebrow')}</p>
          <h1>{t('home.welcomeTitle')}</h1>
          <p className="home-lede">{t('home.welcomeDescription')}</p>
        </div>
        <div className="home-hero-actions">
          <button className="btn" type="button" onClick={openImport}>
            {t('home.importData')}
          </button>
          <button className="btn home-primary" type="button" onClick={openNewProject}>
            {t('home.newProject.open')}
          </button>
        </div>
      </header>

      <div className="home-layout">
        <div className="home-main">
          <section className="card home-projects" aria-labelledby="home-projects-title">
            <div className="home-section-head">
              <h2 id="home-projects-title">{t('home.projects.title')}</h2>
              <button className="btn" type="button" onClick={openNewProject}>
                {t('home.projects.new')}
              </button>
            </div>

            {projectsLoading ? (
              <p className="muted" role="status">
                {t('home.projects.loading')}
              </p>
            ) : projectsError ? (
              <div className="home-error-block" role="alert">
                <p>{t('home.projects.error')}</p>
                <p className="home-hint">{projectsError}</p>
                <button className="btn" type="button" onClick={refreshProjects}>
                  {t('common.retry')}
                </button>
              </div>
            ) : projects.length === 0 ? (
              <p className="muted">{t('home.projects.empty')}</p>
            ) : (
              <div className="project-grid">
                {projects.map((project) => (
                  <ProjectCard
                    key={project.id}
                    project={project}
                    onChanged={refreshProjects}
                  />
                ))}
              </div>
            )}
          </section>

          <section className="card sample-card" aria-labelledby="home-sample-title">
            <div>
              <h2 id="home-sample-title">{t('home.sample.title')}</h2>
              <p className="muted">{t('home.sample.description')}</p>
            </div>
            <div className="sample-actions">
              <button
                className="btn"
                type="button"
                disabled
                title={t('home.sample.unavailable')}
              >
                {t('home.sample.create')}
              </button>
              <p className="home-hint">{t('home.sample.unavailable')}</p>
            </div>
          </section>

          <section
            className="card home-recent-activity"
            aria-labelledby="home-recent-activity-title"
            data-testid="home-recent-activity"
          >
            <div className="home-section-head">
              <h2 id="home-recent-activity-title">
                {t('home.recentActivity.title')}
              </h2>
              <button
                className="btn"
                type="button"
                onClick={() => setActivityDialogOpen(true)}
                disabled={recentActivity.length === 0}
              >
                {t('home.recentActivity.viewAll')}
              </button>
            </div>
            <div
              className="home-activity-filters"
              role="group"
              aria-label={t('home.recentActivity.filtersLabel')}
            >
              {ACTIVITY_FILTERS.map((filter) => (
                <button
                  className="btn"
                  type="button"
                  key={filter}
                  aria-pressed={activityFilter === filter}
                  onClick={() => setActivityFilter(filter)}
                >
                  {t(`home.recentActivity.filters.${filter}`)}
                </button>
              ))}
            </div>
            {renderActivityList(previewActivity, 'home-activity-list')}
          </section>
        </div>

        <aside className="home-side">
          <SystemStatusCard
            status={status}
            loading={statusLoading}
            error={statusError}
            onRetry={refreshStatus}
          />
        </aside>
      </div>

      {dialogOpen ? (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeNewProject()
          }}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-project-title"
            onKeyDown={handleDialogKeyDown}
          >
            <h2 id="new-project-title">{t('home.newProject.title')}</h2>
            <form className="new-project-form" onSubmit={handleCreate}>
              <label htmlFor="new-project-name">{t('home.newProject.nameLabel')}</label>
              <input
                id="new-project-name"
                className="input"
                value={newName}
                placeholder={t('home.newProject.namePlaceholder')}
                onChange={(event) => setNewName(event.target.value)}
                disabled={creating}
                autoFocus
              />
              {createError ? (
                <p className="home-error" role="alert">
                  {createError}
                </p>
              ) : null}
              <div className="modal-actions">
                <button
                  className="btn"
                  type="button"
                  onClick={closeNewProject}
                  disabled={creating}
                >
                  {t('common.cancel')}
                </button>
                <button
                  className="btn home-primary"
                  type="submit"
                  disabled={creating || !newName.trim()}
                >
                  {creating ? t('home.newProject.creating') : t('home.newProject.create')}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {activityDialogOpen ? (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeActivityDialog()
          }}
        >
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="home-all-activity-title"
            onKeyDown={handleActivityDialogKeyDown}
          >
            <div className="home-section-head">
              <h2 id="home-all-activity-title">
                {t('home.recentActivity.allTitle')}
              </h2>
              <button className="btn" type="button" onClick={closeActivityDialog}>
                {t('common.close')}
              </button>
            </div>
            {renderActivityList(filteredActivity, 'home-all-activity-list')}
          </div>
        </div>
      ) : null}
    </section>
  )
}
