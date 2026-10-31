import { useTranslation } from 'react-i18next'

export function P07Reports() {
  const { t } = useTranslation()

  return (
    <section data-testid="page-p07">
      <h1>{t('nav.reports')}</h1>
    </section>
  )
}
