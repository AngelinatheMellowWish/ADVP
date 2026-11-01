import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorMessage } from '../api/projects'
import { getSettings, updateSettings, type Eu2Settings } from '../api/settings'
import { checkForUpdate, type UpdateCheck } from '../api/updates'
import { SettingsSection } from '../components/SettingsSection'

type FieldType = 'text' | 'number' | 'checkbox' | 'select'

type Field = {
  key: string
  section: 'general' | 'workspace' | 'analysis' | 'security' | 'ai'
  type: FieldType
  options?: string[]
}

const FIELDS: Field[] = [
  { key: 'language', section: 'general', type: 'select', options: ['zh', 'en'] },
  { key: 'update_channel', section: 'general', type: 'select', options: ['stable', 'beta'] },
  { key: 'workspace', section: 'workspace', type: 'text' },
  { key: 'analysis_sample_rows', section: 'analysis', type: 'number' },
  { key: 'render_sample_rows', section: 'analysis', type: 'number' },
  { key: 'sandbox_timeout_seconds', section: 'security', type: 'number' },
  { key: 'log_redaction', section: 'security', type: 'checkbox' },
  { key: 'default_provider_id', section: 'ai', type: 'text' },
  { key: 'global_budget', section: 'ai', type: 'number' },
  { key: 'monthly_budget', section: 'ai', type: 'number' },
  { key: 'search_raw_content', section: 'ai', type: 'checkbox' },
  { key: 'search_sensitive', section: 'ai', type: 'checkbox' },
]

const SECTIONS: Field['section'][] = [
  'general',
  'workspace',
  'analysis',
  'security',
  'ai',
]

function valueOf(settings: Eu2Settings | null, key: string): unknown {
  return settings?.[key]?.value
}

function editable(value: unknown, type: FieldType): unknown {
  if (type === 'number') {
    if (value === '' || value === null || value === undefined) return null
    return Number(value)
  }
  if (type === 'checkbox') return Boolean(value)
  return value
}

export function P10Settings() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<Eu2Settings | null>(null)
  const [initial, setInitial] = useState<Eu2Settings | null>(null)
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [update, setUpdate] = useState<UpdateCheck | null>(null)
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
        setValues(
          Object.fromEntries(
            FIELDS.map((field) => [field.key, valueOf(payload, field.key)]),
          ),
        )
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
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

  function isEnv(field: Field): boolean {
    return settings?.[field.key]?.source === 'env'
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
        changes[field.key] = editable(values[field.key], field.type)
      }
      const updated = await updateSettings(changes)
      setSettings(updated)
      setInitial(updated)
      setValues(
        Object.fromEntries(FIELDS.map((field) => [field.key, valueOf(updated, field.key)])),
      )
      setMessage(t('settingsPage.saved'))
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
          </SettingsSection>
        ))}

        <SettingsSection
          title={t('settingsPage.sections.about')}
          description={t('settingsPage.sectionHints.about')}
        >
          <p className="muted">{t('settingsPage.aboutText')}</p>
          <button className="btn" type="button" onClick={() => void runUpdateCheck()} disabled={busy}>
            {t('settingsPage.checkUpdates')}
          </button>
          {update ? (
            <p className="muted" data-testid="update-result">
              {update.available
                ? t('settingsPage.updateAvailable', { version: update.latest })
                : t('settingsPage.upToDate', { version: update.current })}
            </p>
          ) : null}
        </SettingsSection>
      </div>
    </section>
  )
}
