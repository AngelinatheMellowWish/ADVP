import { useTranslation } from 'react-i18next'

import { BudgetSettings } from '../components/BudgetSettings'
import { ProviderPanel } from '../components/ProviderPanel'

export function P08Providers() {
  const { t } = useTranslation()

  return (
    <section className="page" data-testid="page-p08">
      <header className="import-head">
        <div>
          <h1>{t('providersPage.title')}</h1>
          <p className="muted">{t('providersPage.hint')}</p>
        </div>
      </header>
      <div className="report-layout">
        <div className="report-main">
          <ProviderPanel />
        </div>
        <aside className="report-side">
          <BudgetSettings />
        </aside>
      </div>
    </section>
  )
}
