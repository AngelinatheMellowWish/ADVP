import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorMessage } from '../api/projects'
import { getSettings, updateSettings, type Eu2Settings } from '../api/settings'

function numeric(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

export function BudgetSettings() {
  const { t } = useTranslation()
  const [settings, setSettings] = useState<Eu2Settings | null>(null)
  const [globalBudget, setGlobalBudget] = useState('')
  const [monthlyBudget, setMonthlyBudget] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getSettings()
      .then((value) => {
        if (cancelled) return
        setSettings(value)
        const global = numeric(value.global_budget?.value)
        const monthly = numeric(value.monthly_budget?.value)
        setGlobalBudget(global === null ? '' : String(global))
        setMonthlyBudget(monthly === null ? '' : String(monthly))
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function save() {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const updated = await updateSettings({
        global_budget: globalBudget.trim() === '' ? null : Number(globalBudget),
        monthly_budget: monthlyBudget.trim() === '' ? null : Number(monthlyBudget),
      })
      setSettings(updated)
      setMessage(t('providersPage.budget.saved'))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card" aria-label={t('providersPage.budget.title')}>
      <div className="panel-title">
        <div>
          <h2>{t('providersPage.budget.title')}</h2>
          <p className="muted">{t('providersPage.budget.hint')}</p>
        </div>
        {settings?.global_budget?.source === 'env' ? (
          <span className="badge">ENV</span>
        ) : null}
      </div>
      <div className="inline-form">
        <label>
          {t('providersPage.budget.global')}
          <input
            className="input"
            type="number"
            min="0"
            step="0.01"
            value={globalBudget}
            onChange={(event) => setGlobalBudget(event.target.value)}
          />
        </label>
        <label>
          {t('providersPage.budget.monthly')}
          <input
            className="input"
            type="number"
            min="0"
            step="0.01"
            value={monthlyBudget}
            onChange={(event) => setMonthlyBudget(event.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn"
          onClick={() => void save()}
          disabled={busy}
        >
          {t('providersPage.budget.save')}
        </button>
      </div>
      {message ? <p className="notice">{message}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
    </section>
  )
}
