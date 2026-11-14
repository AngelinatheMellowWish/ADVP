import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorMessage } from '../api/projects'
import {
  getSettings,
  resetSettings,
  updateSettings,
  type Eu2Settings,
} from '../api/settings'
import { getAbout, type AboutInfo } from '../api/system'
import { checkForUpdate, type UpdateCheck } from '../api/updates'
import { CleanupPanel } from '../components/CleanupPanel'
import { LicensePanel } from '../components/LicensePanel'
import { SettingsSection } from '../components/SettingsSection'

type FieldType = 'text' | 'number' | 'checkbox' | 'select'

type Field = {
  key: string
  section: 'general' | 'workspace' | 'analysis' | 'security' | 'ai'
  type: FieldType
  options?: string[]
  numeric?: boolean
}

const PIPELINE_KEYS = ['clean', 'analyze', 'report'] as const
const DEFAULT_PIPELINE_OPTIONS = { clean: true, analyze: true, report: true }

const FIELDS: Field[] = [
  { key: 'language', section: 'general', type: 'select', options: ['zh', 'en'] },
  {
    key: 'startup_behavior',
    section: 'general',
    type: 'select',
    options: ['home', 'last_project'],
  },
  { key: 'update_channel', section: 'general', type: 'select', options: ['stable', 'beta'] },
  { key: 'workspace', section: 'workspace', type: 'text' },
  { key: 'analysis_sample_rows', section: 'analysis', type: 'number' },
  { key: 'render_sample_rows', section: 'analysis', type: 'number' },
  { key: 'max_reselects', section: 'analysis', type: 'number' },
  { key: 'analysis_concurrency', section: 'analysis', type: 'number' },
  { key: 'sandbox_timeout_seconds', section: 'security', type: 'number' },
  { key: 'sandbox_max_memory_mb', section: 'security', type: 'number' },
  { key: 'sandbox_max_cpu_seconds', section: 'security', type: 'number' },
  {
    key: 'log_retention_days',
    section: 'security',
    type: 'select',
    options: ['7', '14', '30'],
    numeric: true,
  },
  {
    key: 'log_level',
    section: 'security',
    type: 'select',
    options: ['INFO', 'DEBUG', 'WARN'],
  },
  { key: 'log_redaction', section: 'security', type: 'checkbox' },
  { key: 'default_provider_id', section: 'ai', type: 'text' },
  { key: 'global_budget', section: 'ai', type: 'number' },
  { key: 'monthly_budget', section: 'ai', type: 'number' },
  { key: 'search_raw_content', section: 'ai', type: 'checkbox' },
  { key: 'search_sensitive', section: 'ai', type: 'checkbox' },
]

const SECTIONS: Field['section'][] = ['general', 'workspace', 'analysis', 'security', 'ai']

function valueOf(settings: Eu2Settings | null, key: string): unknown {
  return settings?.[key]?.value
}

function fieldValues(settings: Eu2Settings | null): Record<string, unknown> {
  const result = Object.fromEntries(
    FIELDS.map((field) => [field.key, valueOf(settings, field.key)]),
  )
  result.default_pipeline_options =
    valueOf(settings, 'default_pipeline_options') ?? DEFAULT_PIPELINE_OPTIONS
  return result
}

function editable(value: unknown, field: Field): unknown {
  if (field.type === 'number' || field.numeric) {
    if (value === '' || value === null || value === undefined) return null
    return Number(value)
  }
  if (field.type === 'checkbox') return Boolean(value)
  return value
}

export function P10Settings() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<Eu2Settings | null>(null)
  const [initial, setInitial] = useState<Eu2Settings | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [about, setAbout] = useState<AboutInfo | null>(null)
  const [update, setUpdate] = useState<UpdateCheck | null>(null)
  const [resetConfirm, setResetConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getSettings()
      .then((payload) => {
        if (cancelled) return
        setSettings(payload)
        setInitial(payload)
        setValues(fieldValues(payload))
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
    getAbout()
      .then((payload) => {
        if (!cancelled) setAbout(payload)
      })
      .catch(() => {
        if (!cancelled) setAbout(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const grouped = useMemo(
    () =>
      Object.fromEntries(
        SECTIONS.map((section) => [
          section,
          FIELDS.filter((field) => field.section === section),
        ]),
      ) as Record<Field['section'], Field[]>,
    [],
  )

  const pipelineDefaults = {
    ...DEFAULT_PIPELINE_OPTIONS,
    ...((values.default_pipeline_options as Record<string, boolean> | undefined) ?? {}),
  }

  function isEnv(field: Field): boolean {
    return settings?.[field.key]?.source === 'env'
  }

  function applySettings(updated: Eu2Settings) {
    setSettings(updated)
    setInitial(updated)
    setValues(fieldValues(updated))
  }

  async function save() {
    setBusy(true)
    setMessage(null)
    setError(null)
    try {
      const changes: Record<string, unknown> = {}
      for (const field of FIELDS) {
        if (isEnv(field)) continue
        if (JSON.stringify(values[field.key]) === JSON.stringify(valueOf(initial, field.key))) {
          continue
        }
        changes[field.key] = editable(values[field.key], field)
      }
      if (
        JSON.stringify(values.default_pipeline_options) !==
        JSON.stringify(valueOf(initial, 'default_pipeline_options'))
      ) {
        changes.default_pipeline_options = pipelineDefaults
      }
      const updated = await updateSettings(changes)
      applySettings(updated)
      setMessage(t('settingsPage.saved'))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function reset() {
    setBusy(true)
    setMessage(null)
    setError(null)
    try {
      const updated = await resetSettings()
      applySettings(updated)
      setResetConfirm(false)
      setMessage(t('settingsPage.resetDone'))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function runUpdateCheck() {
    setBusy(true)
    setError(null)
    try {
      setUpdate(await checkForUpdate())
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="page settings-page" data-testid="page-p10">
      <header className="import-head">
        <div>
          <h1>{t('settingsPage.title')}</h1>
          <p className="muted">{t('settingsPage.hint')}</p>
        </div>
        <button className="btn home-primary" type="button" onClick={() => void save()} disabled={busy}>
          {busy ? t('settingsPage.saving') : t('settingsPage.save')}
        </button>
      </header>
      {error ? <p className="error-text">{error}</p> : null}
      {message ? <p className="notice">{message}</p> : null}

      <div className="settings-layout">
        {SECTIONS.map((section) => (
          <SettingsSection
            key={section}
            title={t(`settingsPage.sections.${section}`)}
            description={t(`settingsPage.sectionHints.${section}`)}
          >
            {grouped[section].map((field) => (
              <label key={field.key} className={field.type === 'checkbox' ? 'checkbox-row' : ''}>
                <span>
                  {t(`settingsPage.fields.${field.key}`)}
                  {isEnv(field) ? <span className="badge">ENV</span> : null}
                </span>
                {field.type === 'checkbox' ? (
                  <input
                    type="checkbox"
                    checked={Boolean(values[field.key])}
                    disabled={isEnv(field)}
                    onChange={(event) =>
                      setValues((current) => ({
                        ...current,
                        [field.key]: event.target.checked,
                      }))
                    }
                  />
                ) : field.type === 'select' ? (
                  <select
                    className="input"
                    value={String(values[field.key] ?? '')}
                    disabled={isEnv(field)}
                    onChange={(event) =>
                      setValues((current) => ({
                        ...current,
                        [field.key]: event.target.value,
                      }))
                    }
                  >
                    {field.options?.map((option) => (
                      <option key={option} value={option}>
                        {t(`settingsPage.options.${option}`, { defaultValue: option })}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="input"
                    type={field.type === 'number' ? 'number' : 'text'}
                    value={String(values[field.key] ?? '')}
                    disabled={isEnv(field)}
                    onChange={(event) =>
                      setValues((current) => ({
                        ...current,
                        [field.key]: event.target.value,
                      }))
                    }
                  />
                )}
              </label>
            ))}
            {section === 'analysis' ? (
              <div className="stack-form" data-testid="default-pipeline-options">
                <span>{t('settingsPage.fields.default_pipeline_options')}</span>
                {PIPELINE_KEYS.map((key) => (
                  <label key={key} className="checkbox-row">
                    <span>{t(`settingsPage.pipelineOptions.${key}`)}</span>
                    <input
                      type="checkbox"
                      checked={pipelineDefaults[key] !== false}
                      onChange={(event) =>
                        setValues((current) => ({
                          ...current,
                          default_pipeline_options: {
                            ...pipelineDefaults,
                            [key]: event.target.checked,
                          },
                        }))
                      }
                    />
                  </label>
                ))}
              </div>
            ) : null}
          </SettingsSection>
        ))}

        <SettingsSection
          title={t('settingsPage.sections.about')}
          description={t('settingsPage.sectionHints.about')}
        >
          <p className="muted">{t('settingsPage.aboutText')}</p>
          <div className="settings-meta" data-testid="about-runtime">
            <p>
              <strong>{t('settingsPage.version')}</strong> {about?.version ?? '—'}
            </p>
            <p>
              <strong>{t('settingsPage.runtime')}</strong>{' '}
              {about ? `${about.python} · ${about.platform}` : '—'}
            </p>
            <p>
              <strong>{t('settingsPage.repository')}</strong>{' '}
              {about?.repository.label ?? 'ADVP'}
            </p>
            <p>
              <strong>{t('settingsPage.licenseLabel')}</strong>{' '}
              {about?.license ?? 'Apache-2.0'}
            </p>
          </div>
          <div className="button-row">
            <button className="btn" type="button" onClick={() => void runUpdateCheck()} disabled={busy}>
              {t('settingsPage.checkUpdates')}
            </button>
            <a className="btn" href="/api/diagnostics/bundle" download data-testid="diagnostics-link">
              {t('settingsPage.diagnostics')}
            </a>
          </div>
          {update ? (
            <p className="muted" data-testid="update-result">
              {update.available
                ? t('settingsPage.updateAvailable', { version: update.latest })
                : t('settingsPage.upToDate', { version: update.current })}
            </p>
          ) : null}
          <LicensePanel />
        </SettingsSection>

        <SettingsSection
          title={t('settingsPage.sections.developer')}
          description={t('settingsPage.sectionHints.developer')}
        >
          <p className="muted">{t('settingsPage.developerHint')}</p>
          <div className="button-row">
            <button
              className="btn"
              type="button"
              onClick={() => setResetConfirm(true)}
              disabled={busy}
              data-testid="settings-reset"
            >
              {t('settingsPage.reset')}
            </button>
            <a className="btn" href="/api/diagnostics/bundle" download>
              {t('settingsPage.diagnostics')}
            </a>
          </div>
          {resetConfirm ? (
            <div className="card" data-testid="settings-reset-confirm">
              <p className="error-text">{t('settingsPage.resetWarning')}</p>
              <div className="button-row">
                <button
                  className="btn home-primary"
                  type="button"
                  onClick={() => void reset()}
                  disabled={busy}
                  data-testid="settings-reset-confirm-button"
                >
                  {t('settingsPage.resetConfirm')}
                </button>
                <button className="btn" type="button" onClick={() => setResetConfirm(false)}>
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          ) : null}
          <CleanupPanel />
        </SettingsSection>
      </div>
    </section>
  )
}
