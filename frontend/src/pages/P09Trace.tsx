import { useTranslation } from 'react-i18next'

export function P09Trace() {
  const { t } = useTranslation()

  return (
    <section data-testid="page-p09">
      <h1>{t('nav.trace')}</h1>
    </section>
  )
}
