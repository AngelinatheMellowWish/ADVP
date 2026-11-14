import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { errorMessage } from '../api/projects'
import { getLicenseText, getThirdPartyText } from '../api/system'

export function LicensePanel() {
  const { t } = useTranslation()
  const [license, setLicense] = useState<string | null>(null)
  const [thirdParty, setThirdParty] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([getLicenseText(), getThirdPartyText()])
      .then(([licenseText, thirdPartyText]) => {
        if (!cancelled) {
          setLicense(licenseText)
          setThirdParty(thirdPartyText)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="stack-form" data-testid="license-panel">
      {error ? <p className="error-text">{error}</p> : null}
      <details>
        <summary>{t('settingsPage.license')}</summary>
        <pre className="license-text" data-testid="license-text">
          {license ?? t('settingsPage.loading')}
        </pre>
      </details>
      <details>
        <summary>{t('settingsPage.thirdParty')}</summary>
        <pre className="license-text" data-testid="third-party-text">
          {thirdParty ?? t('settingsPage.loading')}
        </pre>
      </details>
    </div>
  )
}
