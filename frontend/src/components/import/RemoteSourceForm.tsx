import { useEffect, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import {
  errorMessage,
  importRemote,
  importS3,
  type RemoteAuthInput,
} from '../../api/projects'
import { combineS3Key, isValidHttpUrl, parseHeaderLines } from './remoteSourceConfig'

export type RemoteSourceState = 'loading' | 'empty' | 'error' | 'ready'

type RemoteMode = 'http' | 's3'
type AuthMode = 'none' | 'bearer' | 'basic' | 'header'

export function RemoteSourceForm({
  projectId,
  onImported,
  onStateChange,
}: {
  projectId: string
  onImported: (datasetId: string) => void | Promise<void>
  onStateChange?: (state: RemoteSourceState) => void
}) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<RemoteMode>('http')
  const [url, setUrl] = useState('')
  const [authMode, setAuthMode] = useState<AuthMode>('none')
  const [token, setToken] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [headerName, setHeaderName] = useState('')
  const [headerValue, setHeaderValue] = useState('')
  const [customHeaders, setCustomHeaders] = useState('')
  const [timeout, setTimeoutValue] = useState('30')
  const [endpoint, setEndpoint] = useState('')
  const [bucket, setBucket] = useState('')
  const [prefix, setPrefix] = useState('')
  const [key, setKey] = useState('')
  const [region, setRegion] = useState('')
  const [accessKey, setAccessKey] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const hasHttpInput = isValidHttpUrl(url)
  const hasS3Input = bucket.trim().length > 0 && key.trim().length > 0
  const state: RemoteSourceState = busy
    ? 'loading'
    : error
      ? 'error'
      : message
        ? 'ready'
        : mode === 'http'
          ? hasHttpInput
            ? 'ready'
            : 'empty'
          : hasS3Input
            ? 'ready'
            : 'empty'

  useEffect(() => {
    onStateChange?.(state)
  }, [onStateChange, state])

  function timeoutValue(): number {
    const parsed = Number(timeout)
    return Number.isFinite(parsed) ? parsed : Number.NaN
  }

  function buildAuth(): RemoteAuthInput | null {
    if (authMode === 'bearer') {
      const value = token.trim()
      return value ? { type: 'bearer', token: value } : null
    }
    if (authMode === 'basic') {
      const user = username.trim()
      return user ? { type: 'basic', username: user, password } : null
    }
    if (authMode === 'header') {
      const header = headerName.trim()
      return header && headerValue ? { type: 'header', header, value: headerValue } : null
    }
    return null
  }

  function httpProblem(): string | null {
    if (!url.trim()) return 'importPage.remote.needsUrl'
    if (!isValidHttpUrl(url)) return 'importPage.remote.invalidUrl'
    if (authMode === 'bearer' && !token.trim()) return 'importPage.remote.needsToken'
    if (authMode === 'basic' && !username.trim()) return 'importPage.remote.needsUsername'
    if (
      authMode === 'header' &&
      (!headerName.trim() || !headerValue)
    ) {
      return 'importPage.remote.needsHeader'
    }
    const seconds = timeoutValue()
    if (!Number.isFinite(seconds) || seconds < 1 || seconds > 300) {
      return 'importPage.remote.invalidTimeout'
    }
    return null
  }

  function s3Problem(): string | null {
    if (!bucket.trim()) return 'importPage.remote.needsBucket'
    if (!key.trim()) return 'importPage.remote.needsKey'
    if (endpoint.trim() && !isValidHttpUrl(endpoint)) return 'importPage.remote.invalidUrl'
    return null
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitted(true)
    setError(null)
    setMessage(null)
    const problem = mode === 'http' ? httpProblem() : s3Problem()
    if (problem) {
      setError(t(problem))
      return
    }
    setBusy(true)
    try {
      const dataset =
        mode === 'http'
          ? await importRemote(projectId, {
              url: url.trim(),
              name: name.trim() || undefined,
              headers: parseHeaderLines(customHeaders),
              auth: buildAuth(),
              timeout: timeoutValue(),
            })
          : await importS3(projectId, {
              endpoint: endpoint.trim() || undefined,
              bucket: bucket.trim(),
              key: combineS3Key(prefix, key),
              region: region.trim() || undefined,
              accessKey: accessKey.trim() || undefined,
              secretKey: secretKey || undefined,
              name: name.trim() || undefined,
            })
      setMessage(
        t('importPage.remote.importSuccess', {
          name: dataset.name,
          count: dataset.row_count,
        }),
      )
      await onImported(dataset.id)
    } catch (caught) {
      setError(`${t('importPage.remote.importFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(false)
    }
  }

  const urlInvalid = submitted && mode === 'http' && !isValidHttpUrl(url)
  const timeoutInvalid =
    submitted &&
    mode === 'http' &&
    (!Number.isFinite(timeoutValue()) || timeoutValue() < 1 || timeoutValue() > 300)
  const bucketInvalid = submitted && mode === 's3' && !bucket.trim()
  const keyInvalid = submitted && mode === 's3' && !key.trim()

  return (
    <section className="panel remote-source-panel" data-testid="remote-source-form">
      <h3>{t('importPage.remote.title')}</h3>
      <p className="muted">{t('importPage.remote.description')}</p>

      <div
        className="import-mode"
        role="radiogroup"
        aria-label={t('importPage.remote.modeLabel')}
      >
        <label>
          <input
            type="radio"
            name="remote-mode"
            value="http"
            checked={mode === 'http'}
            onChange={() => setMode('http')}
          />{' '}
          {t('importPage.remote.modes.http')}
        </label>
        <label>
          <input
            type="radio"
            name="remote-mode"
            value="s3"
            checked={mode === 's3'}
            onChange={() => setMode('s3')}
          />{' '}
          {t('importPage.remote.modes.s3')}
        </label>
      </div>

      <form className="stack-form" onSubmit={handleSubmit}>
        {mode === 'http' ? (
          <>
            <label htmlFor="remote-url">{t('importPage.remote.urlLabel')}</label>
            <input
              id="remote-url"
              className="input"
              placeholder={t('importPage.remote.urlPlaceholder')}
              value={url}
              aria-invalid={urlInvalid}
              onChange={(event) => setUrl(event.target.value)}
            />
            <p className={urlInvalid ? 'hint error-text' : 'hint'}>
              {t('importPage.remote.urlHint')}
            </p>

            <label htmlFor="remote-auth">{t('importPage.remote.authLabel')}</label>
            <select
              id="remote-auth"
              className="input"
              value={authMode}
              onChange={(event) => setAuthMode(event.target.value as AuthMode)}
            >
              <option value="none">{t('importPage.remote.authModes.none')}</option>
              <option value="bearer">{t('importPage.remote.authModes.bearer')}</option>
              <option value="basic">{t('importPage.remote.authModes.basic')}</option>
              <option value="header">{t('importPage.remote.authModes.header')}</option>
            </select>

            {authMode === 'bearer' ? (
              <>
                <label htmlFor="remote-token">{t('importPage.remote.tokenLabel')}</label>
                <input
                  id="remote-token"
                  className="input"
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                />
              </>
            ) : null}

            {authMode === 'basic' ? (
              <>
                <label htmlFor="remote-username">
                  {t('importPage.remote.usernameLabel')}
                </label>
                <input
                  id="remote-username"
                  className="input"
                  autoComplete="off"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                />
                <label htmlFor="remote-password">
                  {t('importPage.remote.passwordLabel')}
                </label>
                <input
                  id="remote-password"
                  className="input"
                  type="password"
                  autoComplete="off"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </>
            ) : null}

            {authMode === 'header' ? (
              <>
                <label htmlFor="remote-header-name">
                  {t('importPage.remote.headerNameLabel')}
                </label>
                <input
                  id="remote-header-name"
                  className="input"
                  value={headerName}
                  onChange={(event) => setHeaderName(event.target.value)}
                />
                <label htmlFor="remote-header-value">
                  {t('importPage.remote.headerValueLabel')}
                </label>
                <input
                  id="remote-header-value"
                  className="input"
                  type="password"
                  autoComplete="off"
                  value={headerValue}
                  onChange={(event) => setHeaderValue(event.target.value)}
                />
              </>
            ) : null}

            <label htmlFor="remote-headers">{t('importPage.remote.headersLabel')}</label>
            <textarea
              id="remote-headers"
              rows={3}
              value={customHeaders}
              placeholder={t('importPage.remote.headersPlaceholder')}
              onChange={(event) => setCustomHeaders(event.target.value)}
            />
            <p className="hint">{t('importPage.remote.headersHint')}</p>

            <label htmlFor="remote-timeout">{t('importPage.remote.timeoutLabel')}</label>
            <input
              id="remote-timeout"
              className="input"
              type="number"
              min="1"
              max="300"
              value={timeout}
              aria-invalid={timeoutInvalid}
              onChange={(event) => setTimeoutValue(event.target.value)}
            />
            <p className={timeoutInvalid ? 'hint error-text' : 'hint'}>
              {t('importPage.remote.timeoutHint')}
            </p>
          </>
        ) : (
          <>
            <label htmlFor="s3-endpoint">{t('importPage.remote.endpointLabel')}</label>
            <input
              id="s3-endpoint"
              className="input"
              placeholder={t('importPage.remote.endpointPlaceholder')}
              value={endpoint}
              onChange={(event) => setEndpoint(event.target.value)}
            />

            <label htmlFor="s3-bucket">{t('importPage.remote.bucketLabel')}</label>
            <input
              id="s3-bucket"
              className="input"
              value={bucket}
              aria-invalid={bucketInvalid}
              onChange={(event) => setBucket(event.target.value)}
            />

            <label htmlFor="s3-prefix">{t('importPage.remote.prefixLabel')}</label>
            <input
              id="s3-prefix"
              className="input"
              value={prefix}
              onChange={(event) => setPrefix(event.target.value)}
            />

            <label htmlFor="s3-key">{t('importPage.remote.keyLabel')}</label>
            <input
              id="s3-key"
              className="input"
              value={key}
              aria-invalid={keyInvalid}
              onChange={(event) => setKey(event.target.value)}
            />

            <label htmlFor="s3-region">{t('importPage.remote.regionLabel')}</label>
            <input
              id="s3-region"
              className="input"
              value={region}
              onChange={(event) => setRegion(event.target.value)}
            />

            <label htmlFor="s3-access-key">{t('importPage.remote.accessKeyLabel')}</label>
            <input
              id="s3-access-key"
              className="input"
              autoComplete="off"
              value={accessKey}
              onChange={(event) => setAccessKey(event.target.value)}
            />

            <label htmlFor="s3-secret-key">{t('importPage.remote.secretKeyLabel')}</label>
            <input
              id="s3-secret-key"
              className="input"
              type="password"
              autoComplete="off"
              value={secretKey}
              onChange={(event) => setSecretKey(event.target.value)}
            />
            <p className="hint">{t('importPage.remote.s3TimeoutHint')}</p>
          </>
        )}

        <label htmlFor="remote-name">{t('importPage.remote.nameLabel')}</label>
        <input
          id="remote-name"
          className="input"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />

        <div className="import-actions">
          <button className="btn home-primary" type="submit" disabled={busy}>
            {busy ? t('importPage.remote.importing') : t('importPage.remote.import')}
          </button>
        </div>
      </form>

      {message ? <p className="muted">{message}</p> : null}
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  )
}
