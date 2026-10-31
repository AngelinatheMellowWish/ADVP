import { useTranslation } from 'react-i18next'

export function P08Providers() {
  const { t } = useTranslation()

  return (
    <section data-testid="page-p08">
      <h1>{t('nav.providers')}</h1>
    </section>
  )
}
