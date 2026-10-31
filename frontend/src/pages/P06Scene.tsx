import { useTranslation } from 'react-i18next'

export function P06Scene() {
  const { t } = useTranslation()

  return (
    <section data-testid="page-p06">
      <h1>{t('nav.scene')}</h1>
    </section>
  )
}
