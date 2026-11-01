import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'

type PaletteAction = {
  id: string
  label: string
  keywords?: string
  disabled?: boolean
  reason?: string
  run?: () => void
}

function firstEnabledIndex(actions: PaletteAction[]): number {
  const index = actions.findIndex((action) => !action.disabled)
  return index < 0 ? 0 : index
}

function optionId(action: PaletteAction): string {
  return `palette-option-${action.id}`
}

function hasOpenModal(): boolean {
  return document.querySelector('[role="dialog"][aria-modal="true"]') !== null
}

export function CommandPalette() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { projectId } = useParams<{ projectId?: string }>()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const dialogRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)

  const actions = useMemo<PaletteAction[]>(() => {
    const projectAction = (id: string, labelKey: string, path: string): PaletteAction => {
      if (!projectId) {
        return {
          id,
          label: t(labelKey),
          keywords: path,
          disabled: true,
          reason: t('palette.selectProject'),
        }
      }
      return {
        id,
        label: t(labelKey),
        keywords: path,
        run: () => navigate(`/projects/${encodeURIComponent(projectId)}/${path}`),
      }
    }

    const isChinese = i18n.language.toLowerCase().startsWith('zh')

    return [
      {
        id: 'p01',
        label: t('nav.home'),
        keywords: 'p01 home',
        run: () => navigate('/'),
      },
      projectAction('p02', 'nav.import', 'import'),
      projectAction('p03', 'nav.data', 'data'),
      projectAction('p04', 'nav.pipeline', 'pipeline'),
      projectAction('p05', 'nav.charts', 'charts'),
      projectAction('p06', 'nav.scene', 'scene'),
      projectAction('p07', 'nav.reports', 'reports'),
      {
        id: 'p08',
        label: t('nav.providers'),
        keywords: 'p08 settings providers',
        run: () => navigate('/settings/providers'),
      },
      projectAction('p09', 'nav.trace', 'trace'),
      {
        id: 'p10',
        label: t('nav.settings'),
        keywords: 'p10 settings',
        run: () => navigate('/settings'),
      },
      {
        id: 'switch-language',
        label: t('palette.switchLanguage'),
        keywords: `${isChinese ? 'en' : 'zh'} language`,
        run: () => {
          void i18n.changeLanguage(isChinese ? 'en' : 'zh')
        },
      },
      {
        id: 'new-project',
        label: t('palette.newProject'),
        disabled: true,
        reason: t('palette.unavailable'),
      },
      {
        id: 'run-pipeline',
        label: t('palette.runPipeline'),
        disabled: true,
        reason: t('palette.usePipelinePage'),
      },
      {
        id: 'export',
        label: t('palette.export'),
        disabled: true,
        reason: t('palette.useReportsPage'),
      },
      {
        id: 'close-service',
        label: t('palette.closeService'),
        disabled: true,
        reason: t('palette.useSettingsPage'),
      },
    ]
  }, [i18n, navigate, projectId, t])

  const normalizedQuery = query.trim().toLowerCase()
  const filtered = useMemo(() => {
    if (!normalizedQuery) return actions
    return actions.filter((action) =>
      `${action.label} ${action.keywords ?? ''}`.toLowerCase().includes(normalizedQuery),
    )
  }, [actions, normalizedQuery])
  const activeAction = filtered[activeIndex]
  const activeOptionId = activeAction ? optionId(activeAction) : undefined

  useEffect(() => {
    if (!open) return
    setActiveIndex(firstEnabledIndex(filtered))
  }, [filtered, open])

  useEffect(() => {
    if (!open) return
    previousFocus.current = document.activeElement as HTMLElement | null
    const timeout = window.setTimeout(() => inputRef.current?.focus(), 0)
    return () => {
      window.clearTimeout(timeout)
      previousFocus.current?.focus?.()
    }
  }, [open])

  useEffect(() => {
    function openPalette() {
      if (open) {
        setOpen(false)
        return
      }
      if (hasOpenModal()) return
      setOpen(true)
    }

    function handleKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        openPalette()
        return
      }
      if (event.key === 'Escape' && open) {
        event.preventDefault()
        setOpen(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('advp:open-command-palette', openPalette)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('advp:open-command-palette', openPalette)
    }
  }, [open])

  function close() {
    setOpen(false)
  }

  function run(action: PaletteAction) {
    if (action.disabled || !action.run) return
    close()
    action.run()
  }

  function moveActive(direction: 1 | -1) {
    if (filtered.length === 0) return
    setActiveIndex((current) => {
      let next = current
      for (let step = 0; step < filtered.length; step += 1) {
        next = (next + direction + filtered.length) % filtered.length
        if (!filtered[next].disabled) return next
      }
      return current
    })
  }

  function handleDialogKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      moveActive(1)
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      moveActive(-1)
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const action = filtered[activeIndex]
      if (action) run(action)
      return
    }
    if (event.key === 'Tab') {
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input, [href], [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable || focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
  }

  if (!open) return null

  return (
    <div
      className="palette-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close()
      }}
    >
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label={t('palette.title')}
        ref={dialogRef}
        onKeyDown={handleDialogKeyDown}
      >
        <div className="palette-header">
          <h2 className="palette-title">{t('palette.title')}</h2>
          <button
            className="btn palette-close"
            type="button"
            aria-label={t('common.close')}
            onClick={close}
          >
            ×
          </button>
        </div>
        <input
          className="input palette-input"
          type="search"
          role="combobox"
          value={query}
          placeholder={t('palette.placeholder')}
          aria-label={t('palette.placeholder')}
          aria-autocomplete="list"
          aria-expanded="true"
          aria-controls="palette-actions"
          aria-activedescendant={activeOptionId}
          autoComplete="off"
          onChange={(event) => setQuery(event.target.value)}
          ref={inputRef}
        />
        <ul id="palette-actions" className="palette-list" role="listbox" aria-label={t('palette.title')}>
          {filtered.map((action, index) => (
            <li
              id={optionId(action)}
              className={
                index === activeIndex
                  ? 'palette-option active'
                  : 'palette-option'
              }
              role="option"
              aria-selected={index === activeIndex}
              aria-disabled={action.disabled ? 'true' : undefined}
              key={action.id}
              onMouseEnter={() => {
                if (!action.disabled) setActiveIndex(index)
              }}
              onMouseDown={(event) => {
                event.preventDefault()
                run(action)
              }}
            >
              <span className="palette-option-label">{action.label}</span>
              {action.disabled && action.reason ? (
                <span className="palette-reason">{action.reason}</span>
              ) : null}
            </li>
          ))}
        </ul>
        {filtered.length === 0 ? (
          <p className="muted palette-empty">{t('palette.noResults')}</p>
        ) : null}
      </div>
    </div>
  )
}
