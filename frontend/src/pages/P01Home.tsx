import { useEffect, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import {
  createProject,
  errorMessage,
  listProjects,
  type ProjectSummary,
} from '../api/projects'
import { getSystemStatus, type SystemStatus } from '../api/system'
import { ProjectCard } from '../components/ProjectCard'
import { SystemStatusCard } from '../components/SystemStatusCard'

export function P01Home() {
  const { t } = useTranslation()
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

  function refreshProjects() {
    setProjectsReload((value) => value + 1)
  }

  function refreshStatus() {
    setStatusReload((value) => value + 1)
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

  return (
    <section className="home-page" data-testid="page-p01">
      <header className="home-hero">
        <div className="home-hero-copy">
          <p className="home-eyebrow">{t('home.eyebrow')}</p>
          <h1>{t('home.welcomeTitle')}</h1>
          <p className="home-lede">{t('home.welcomeDescription')}</p>
        </div>
        <div className="home-hero-actions">
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

          <section className="card" aria-labelledby="home-recent-tasks-title">
            <h2 id="home-recent-tasks-title">{t('home.recentTasks.title')}</h2>
            <p className="muted">{t('home.recentTasks.empty')}</p>
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
    </section>
  )
}
