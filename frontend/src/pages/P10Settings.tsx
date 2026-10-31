import { useTranslation } from 'react-i18next'

export function P10Settings() {
  const { t } = useTranslation()

  return (
    <section data-testid="page-p10">
      <h1>{t('nav.settings')}</h1>
    </section>
  )
}
