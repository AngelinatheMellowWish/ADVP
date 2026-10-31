import { useTranslation } from 'react-i18next'
import { useParams, useLocation } from 'react-router-dom'

import { NotificationCenter } from './NotificationCenter'
import { useProject } from './projectContext'

const PAGE_LABELS: { pattern: RegExp; key: string }[] = [
  { pattern: /^\/$/, key: 'nav.home' },
  { pattern: /^\/projects\/[^/]+\/import\/?$/, key: 'nav.import' },
  { pattern: /^\/projects\/[^/]+\/data\/?$/, key: 'nav.data' },
  { pattern: /^\/projects\/[^/]+\/pipeline\/?$/, key: 'nav.pipeline' },
  { pattern: /^\/projects\/[^/]+\/charts\/?$/, key: 'nav.charts' },
  { pattern: /^\/projects\/[^/]+\/scene\/?$/, key: 'nav.scene' },
  { pattern: /^\/projects\/[^/]+\/reports\/?$/, key: 'nav.reports' },
  { pattern: /^\/projects\/[^/]+\/trace\/?$/, key: 'nav.trace' },
  { pattern: /^\/settings\/providers\/?$/, key: 'nav.providers' },
  { pattern: /^\/settings\/?$/, key: 'nav.settings' },
]

export function Topbar() {
  const { t, i18n } = useTranslation()
  const { project, loading, error, refresh } = useProject()
  const { projectId } = useParams<{ projectId?: string }>()
  const { pathname } = useLocation()

  const pageKey = PAGE_LABELS.find((entry) => entry.pattern.test(pathname))?.key
  const pageLabel = pageKey ? t(pageKey) : null
  const isChinese = i18n.language.toLowerCase().startsWith('zh')

  const crumbs: string[] = []
  if (projectId) {
    if (project) {
      crumbs.push(project.name)
    }
  } else if (pathname.startsWith('/settings')) {
    crumbs.push(t('nav.settings'))
  }
  if (pageLabel && pageLabel !== crumbs[crumbs.length - 1]) {
    crumbs.push(pageLabel)
  }

  function toggleLanguage() {
    void i18n.changeLanguage(isChinese ? 'en' : 'zh')
  }

  return (
    <header className="topbar">
      <div className="topbar-context">
        <nav className="topbar-title" aria-label={t('nav.breadcrumb')}>
          <ol>
            {crumbs.map((crumb, index) => (
              <li key={`${crumb}-${index}`}>
                {index > 0 ? (
                  <span className="muted" aria-hidden="true">
                    /
                  </span>
                ) : null}
                <span>{crumb}</span>
              </li>
            ))}
          </ol>
        </nav>
        {projectId ? (
          loading ? (
            <span className="project-status" role="status">
              {t('project.loading')}
            </span>
          ) : error || !project ? (
            <span className="project-status" role="alert">
              <span>{t('project.error')}</span>
              <button className="btn" type="button" onClick={refresh}>
                {t('common.retry')}
              </button>
            </span>
          ) : null
        ) : null}
      </div>
      <div className="topbar-actions">
        <button
          className="btn command-trigger"
          type="button"
          aria-label={t('palette.open')}
          aria-keyshortcuts="Control+K Meta+K"
          title={`${t('palette.open')} (Ctrl+K)`}
          onClick={() => window.dispatchEvent(new Event('advp:open-command-palette'))}
        >
          <span className="command-trigger-label">{t('palette.open')}</span>
          <kbd className="command-trigger-hint" aria-hidden="true">
            Ctrl K
          </kbd>
        </button>
        <NotificationCenter />
        <button
          className="btn"
          type="button"
          onClick={toggleLanguage}
          aria-label={t('topbar.language')}
        >
          {isChinese ? 'EN' : '中文'}
        </button>
        <button
          className="btn"
          type="button"
          disabled
          title={t('topbar.help')}
        >
          {t('topbar.help')}
        </button>
        <span className="muted" data-testid="system-status">
          {t('topbar.statusLocal')}
        </span>
        <button
          className="btn"
          type="button"
          disabled
          title={t('topbar.closeService')}
        >
          {t('topbar.closeService')}
        </button>
      </div>
    </header>
  )
}
