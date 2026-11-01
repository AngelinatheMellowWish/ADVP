import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import {
  deleteProject,
  errorMessage,
  revealProject,
  updateProject,
  type ProjectSummary,
} from '../api/projects'

type ProjectCardProps = {
  project: ProjectSummary
  onChanged: () => void
}

function formatUpdated(value: string, language: string): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat(language, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function ProjectCard({ project, onChanged }: ProjectCardProps) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const [renaming, setRenaming] = useState(false)
  const [name, setName] = useState(project.name)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updated = formatUpdated(project.updated_at, i18n.language)
  const revealReasonId = `project-${project.id}-reveal-reason`
  const sourceTypes = Array.isArray(project.source_types) ? project.source_types : []
  const sourceLabel =
    sourceTypes.length > 0
      ? sourceTypes
          .map((type) =>
            t(`home.project.sourceTypes.${type}`, { defaultValue: type }),
          )
          .join(', ')
      : project.dataset_count > 0
        ? t('home.project.dataSourceUnknown')
        : t('home.project.noDataSources')

  function openProject() {
    const path = project.dataset_count > 0 ? 'data' : 'import'
    navigate(`/projects/${encodeURIComponent(project.id)}/${path}`)
  }

  function startRename() {
    setName(project.name)
    setError(null)
    setRenaming(true)
  }

  async function saveRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    if (trimmed === project.name) {
      setRenaming(false)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await updateProject(project.id, { name: trimmed })
      setRenaming(false)
      onChanged()
    } catch (caught) {
      setError(`${t('home.project.renameFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function toggleArchive() {
    setBusy(true)
    setError(null)
    try {
      await updateProject(project.id, { archived: !project.archived })
      onChanged()
    } catch (caught) {
      setError(`${t('home.project.archiveFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function revealFolder() {
    setBusy(true)
    setError(null)
    try {
      await revealProject(project.id)
    } catch (caught) {
      setError(`${t('home.project.revealFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  async function removeProject() {
    if (!window.confirm(t('home.project.confirmDelete', { name: project.name }))) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await deleteProject(project.id)
      onChanged()
    } catch (caught) {
      setError(`${t('home.project.deleteFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="project-card" data-testid={`project-card-${project.id}`}>
      <div className="project-card-thumb" aria-hidden="true">
        <span className="project-card-thumb-label">{t('home.project.thumbnail')}</span>
      </div>
      <div className="project-card-body">
        <div className="project-card-title-row">
          <h3 className="project-card-title">{project.name}</h3>
          <span
            className={
              project.archived
                ? 'status-pill status-pill-muted'
                : 'status-pill status-pill-ok'
            }
          >
            {project.archived ? t('home.project.archived') : t('home.project.active')}
          </span>
        </div>
        <p className="project-card-meta">
          <span>
            {t('home.project.dataSource')}: {sourceLabel}
          </span>
          <span>{t('home.project.datasetCount', { count: project.dataset_count })}</span>
        </p>
        <p className="project-card-updated">
          {updated
            ? t('home.project.updated', { date: updated })
            : t('home.project.updatedUnknown')}
        </p>

        {renaming ? (
          <form className="project-rename" onSubmit={saveRename}>
            <label className="project-rename-label" htmlFor={`rename-${project.id}`}>
              {t('home.project.renameLabel')}
            </label>
            <input
              id={`rename-${project.id}`}
              className="input"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={busy}
              autoFocus
            />
            <div className="project-rename-actions">
              <button className="btn" type="submit" disabled={busy || !name.trim()}>
                {t('home.project.save')}
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => setRenaming(false)}
                disabled={busy}
              >
                {t('common.cancel')}
              </button>
            </div>
          </form>
        ) : (
          <div
            className="project-card-actions"
            role="group"
            aria-label={t('home.project.actionsLabel', { name: project.name })}
          >
            <button className="btn" type="button" onClick={openProject} disabled={busy}>
              {t('home.project.open')}
            </button>
            <button
              className="btn"
              type="button"
              onClick={startRename}
              disabled={busy}
              aria-label={`${t('home.project.rename')}: ${project.name}`}
            >
              {t('home.project.rename')}
            </button>
            <button className="btn" type="button" onClick={toggleArchive} disabled={busy}>
              {project.archived
                ? t('home.project.unarchive')
                : t('home.project.archive')}
            </button>
            <button
              className="btn project-card-danger"
              type="button"
              onClick={removeProject}
              disabled={busy}
            >
              {t('home.project.delete')}
            </button>
            <button
              className="btn"
              type="button"
              onClick={revealFolder}
              disabled={busy || project.dataset_count === 0}
              aria-describedby={
                project.dataset_count === 0 ? revealReasonId : undefined
              }
              title={
                project.dataset_count === 0
                  ? t('home.project.openDirectoryNoData')
                  : t('home.project.openDirectory')
              }
            >
              {t('home.project.openDirectory')}
            </button>
          </div>
        )}

        {!renaming && project.dataset_count === 0 ? (
          <p className="home-hint" id={revealReasonId}>
            {t('home.project.openDirectoryNoData')}
          </p>
        ) : null}

        {error ? (
          <p className="home-error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </article>
  )
}
