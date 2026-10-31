import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import { useTasks } from './taskContext'

type TaskEntry = {
  key: 'imports' | 'pipelines' | 'exports' | 'render_jobs' | 'live_streams'
  labelKey: string
  path: string
}

const TASK_ENTRIES: TaskEntry[] = [
  { key: 'imports', labelKey: 'tasks.imports', path: 'import' },
  { key: 'pipelines', labelKey: 'tasks.pipelines', path: 'pipeline' },
  { key: 'exports', labelKey: 'tasks.exports', path: 'reports' },
  { key: 'render_jobs', labelKey: 'tasks.renderJobs', path: 'scene' },
  { key: 'live_streams', labelKey: 'tasks.liveStreams', path: 'data' },
]

export function TaskBar() {
  const { t } = useTranslation()
  const { projectId } = useParams<{ projectId?: string }>()
  const { tasks, total } = useTasks()

  if (total === 0) return null

  return (
    <div className="taskbar" data-testid="taskbar" role="region" aria-label={t('tasks.title')}>
      <span className="taskbar-title">{t('tasks.title')}</span>
      <ul className="taskbar-list">
        {TASK_ENTRIES.filter((entry) => tasks[entry.key] > 0).map((entry) => {
          const content = (
            <>
              <span>{t(entry.labelKey)}</span>
              <span className="taskbar-count">{tasks[entry.key]}</span>
            </>
          )
          return (
            <li key={entry.key}>
              {projectId ? (
                <Link
                  className="taskbar-link"
                  to={`/projects/${encodeURIComponent(projectId)}/${entry.path}`}
                >
                  {content}
                </Link>
              ) : (
                <span
                  className="taskbar-chip taskbar-chip-disabled"
                  aria-disabled="true"
                  title={t('topbar.selectProject')}
                >
                  {content}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
