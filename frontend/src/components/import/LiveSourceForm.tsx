import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'

import {
  createLiveSession,
  getLiveSession,
  saveLiveSnapshot,
  stopLiveSession,
  type LiveSession,
  type LiveSessionInput,
} from '../../api/live'
import {
  errorMessage,
  previewKafka,
  previewWebSocket,
  type StreamPreviewResponse,
} from '../../api/projects'

export type LiveSourceState = 'loading' | 'empty' | 'error' | 'ready'

type LiveKind = 'websocket' | 'kafka'
type MessageFormat = 'auto' | 'json' | 'jsonl'
type BusyState = 'preview' | 'import' | null
type FieldMapping = { include: boolean; name: string }

const MESSAGE_FORMATS: MessageFormat[] = ['auto', 'json', 'jsonl']
const POLL_ATTEMPTS = 20
const POLL_INTERVAL_MS = 300

function isWebSocketUrl(value: string): boolean {
  return /^wss?:\/\//i.test(value.trim())
}

function fieldKeys(records: Record<string, unknown>[]): string[] {
  return Array.from(new Set(records.flatMap((record) => Object.keys(record))))
}

function defaultFields(records: Record<string, unknown>[]) {
  const keys = fieldKeys(records)
  const sample = records[0] ?? {}
  const x =
    keys.find((key) => /time|timestamp|ts|date/i.test(key)) ??
    keys.find((key) => typeof sample[key] === 'string') ??
    keys[0] ??
    ''
  const y =
    keys.find((key) => key !== x && typeof sample[key] === 'number') ??
    keys.find((key) => key !== x) ??
    ''
  const series = keys.find(
    (key) => key !== x && key !== y && typeof sample[key] === 'string',
  )
  return { x, y, series: series ?? '' }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export function LiveSourceForm({
  projectId,
  onImported,
  onStateChange,
}: {
  projectId: string
  onImported: (datasetId: string) => void | Promise<void>
  onStateChange?: (state: LiveSourceState) => void
}) {
  const { t } = useTranslation()
  const [kind, setKind] = useState<LiveKind>('websocket')
  const [url, setUrl] = useState('')
  const [bootstrap, setBootstrap] = useState('')
  const [topic, setTopic] = useState('')
  const [messageFormat, setMessageFormat] = useState<MessageFormat>('auto')
  const [windowSize, setWindowSize] = useState('50')
  const [timeout, setTimeoutValue] = useState('10')
  const [preview, setPreview] = useState<StreamPreviewResponse | null>(null)
  const [xField, setXField] = useState('')
  const [yField, setYField] = useState('')
  const [seriesField, setSeriesField] = useState('')
  const [fieldMapping, setFieldMapping] = useState<Record<string, FieldMapping>>({})
  const [name, setName] = useState('')
  const [busy, setBusy] = useState<BusyState>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const fields = useMemo(
    () => fieldKeys(preview?.records ?? []),
    [preview?.records],
  )

  const state: LiveSourceState = busy
    ? 'loading'
    : error
      ? 'error'
      : preview
        ? 'ready'
        : 'empty'

  useEffect(() => {
    onStateChange?.(state)
  }, [onStateChange, state])

  function windowValue(): number {
    return Number(windowSize)
  }

  function timeoutValue(): number {
    return Number(timeout)
  }

  function validationProblem(): string | null {
    if (kind === 'websocket') {
      if (!isWebSocketUrl(url)) return 'importPage.live.needsAddress'
    } else {
      if (!bootstrap.trim()) return 'importPage.live.needsBootstrap'
      if (!topic.trim()) return 'importPage.live.needsTopic'
    }
    const messages = windowValue()
    if (!Number.isInteger(messages) || messages < 1 || messages > 5000) {
      return 'importPage.live.invalidWindow'
    }
    const seconds = timeoutValue()
    if (!Number.isFinite(seconds) || seconds < 1 || seconds > 120) {
      return 'importPage.live.invalidTimeout'
    }
    return null
  }

  function applyPreview(response: StreamPreviewResponse) {
    const defaults = defaultFields(response.records)
    setPreview(response)
    setXField(defaults.x)
    setYField(defaults.y)
    setSeriesField(defaults.series)
    setFieldMapping(
      Object.fromEntries(
        fieldKeys(response.records).map((key) => [key, { include: true, name: key }]),
      ),
    )
  }

  function updateFieldMapping(key: string, next: Partial<FieldMapping>) {
    setFieldMapping((current) => ({
      ...current,
      [key]: {
        include: current[key]?.include ?? true,
        name: current[key]?.name ?? key,
        ...next,
      },
    }))
  }

  function mappingPayload(): Record<string, string | null> {
    return Object.fromEntries(
      fields.map((key) => {
        const entry = fieldMapping[key]
        if (entry && !entry.include) return [key, null]
        return [key, entry?.name.trim() || key]
      }),
    )
  }

  async function handlePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setMessage(null)
    const problem = validationProblem()
    if (problem) {
      setError(t(problem))
      return
    }
    setBusy('preview')
    setPreview(null)
    try {
      const response =
        kind === 'websocket'
          ? await previewWebSocket(url.trim(), windowValue(), timeoutValue())
          : await previewKafka(
              bootstrap.trim(),
              topic.trim(),
              windowValue(),
              timeoutValue(),
            )
      applyPreview(response)
    } catch (caught) {
      setError(`${t('importPage.live.previewFailed')} ${errorMessage(caught)}`)
    } finally {
      setBusy(null)
    }
  }

  function buildSessionInput(): LiveSessionInput {
    const common: LiveSessionInput = {
      kind,
      max_messages: windowValue(),
      sample_interval_ms: 0,
      timeout: timeoutValue(),
      auto_offset_reset: 'earliest',
    }
    if (kind === 'websocket') {
      return { ...common, url: url.trim(), headers: {} }
    }
    return {
      ...common,
      bootstrap: bootstrap.trim(),
      topic: topic.trim(),
    }
  }

  async function handleImport() {
    setError(null)
    setMessage(null)
    const problem = validationProblem()
    if (problem) {
      setError(t(problem))
      return
    }
    if (!preview) {
      setError(t('importPage.live.previewRequired'))
      return
    }
    setBusy('import')
    let session: LiveSession | null = null
    try {
      session = await createLiveSession(buildSessionInput())
      let latest = session
      for (let attempt = 0; attempt < POLL_ATTEMPTS && latest.count === 0; attempt += 1) {
        await delay(POLL_INTERVAL_MS)
        latest = await getLiveSession(session.session_id)
      }
      if (latest.count === 0) {
        setError(t('importPage.live.emptySnapshot'))
        return
      }
      const dataset = await saveLiveSnapshot(
        session.session_id,
        projectId,
        name.trim() || undefined,
        mappingPayload(),
      )
      setMessage(
        t('importPage.live.importSuccess', {
          name: dataset.name,
          count: dataset.row_count,
        }),
      )
      await onImported(dataset.id)
    } catch (caught) {
      setError(`${t('importPage.live.importFailed')} ${errorMessage(caught)}`)
    } finally {
      if (session) {
        try {
          await stopLiveSession(session.session_id)
        } catch {
          // Best-effort cleanup; the import result is already known.
        }
      }
      setBusy(null)
    }
  }

  return (
    <section className="panel remote-source-panel" data-testid="live-source-form">
      <h3>{t('importPage.live.title')}</h3>
      <p className="muted">{t('importPage.live.description')}</p>

      <form className="stack-form" onSubmit={handlePreview}>
        <fieldset className="live-protocol">
          <legend>{t('importPage.live.protocolLabel')}</legend>
          <label>
            <input
              type="radio"
              name="live-kind"
              value="websocket"
              checked={kind === 'websocket'}
              onChange={() => setKind('websocket')}
            />
            {t('importPage.live.protocols.websocket')}
          </label>
          <label>
            <input
              type="radio"
              name="live-kind"
              value="kafka"
              checked={kind === 'kafka'}
              onChange={() => setKind('kafka')}
            />
            {t('importPage.live.protocols.kafka')}
          </label>
        </fieldset>

        {kind === 'websocket' ? (
          <>
            <label htmlFor="live-address">{t('importPage.live.addressLabel')}</label>
            <input
              id="live-address"
              className="input"
              placeholder={t('importPage.live.addressPlaceholder')}
              value={url}
              onChange={(event) => setUrl(event.target.value)}
            />
          </>
        ) : (
          <>
            <label htmlFor="live-bootstrap">{t('importPage.live.bootstrapLabel')}</label>
            <input
              id="live-bootstrap"
              className="input"
              placeholder={t('importPage.live.bootstrapPlaceholder')}
              value={bootstrap}
              onChange={(event) => setBootstrap(event.target.value)}
            />
            <label htmlFor="live-topic">{t('importPage.live.topicLabel')}</label>
            <input
              id="live-topic"
              className="input"
              placeholder={t('importPage.live.topicPlaceholder')}
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
            />
          </>
        )}

        <label htmlFor="live-format">{t('importPage.live.messageFormatLabel')}</label>
        <select
          id="live-format"
          className="input"
          value={messageFormat}
          onChange={(event) => setMessageFormat(event.target.value as MessageFormat)}
        >
          {MESSAGE_FORMATS.map((format) => (
            <option key={format} value={format}>
              {t(`importPage.live.messageFormats.${format}`)}
            </option>
          ))}
        </select>
        <p className="hint">{t('importPage.live.messageFormatHint')}</p>

        <label htmlFor="live-window">{t('importPage.live.windowSizeLabel')}</label>
        <input
          id="live-window"
          className="input"
          type="number"
          min="1"
          max="5000"
          value={windowSize}
          onChange={(event) => setWindowSize(event.target.value)}
        />
        <p className="hint">{t('importPage.live.windowSizeHint')}</p>

        <label htmlFor="live-timeout">{t('importPage.live.timeoutLabel')}</label>
        <input
          id="live-timeout"
          className="input"
          type="number"
          min="1"
          max="120"
          value={timeout}
          onChange={(event) => setTimeoutValue(event.target.value)}
        />
        <p className="hint">{t('importPage.live.timeoutHint')}</p>

        <div className="import-actions">
          <button className="btn" type="submit" disabled={busy !== null}>
            {busy === 'preview'
              ? t('importPage.live.testing')
              : t('importPage.live.test')}
          </button>
        </div>
      </form>

      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
      {message ? <p className="muted">{message}</p> : null}

      {preview ? (
        <div className="import-live-result">
          <h4>{t('importPage.live.previewTitle')}</h4>
          <p className="hint">
            {t('importPage.live.previewSummary', {
              count: preview.count,
              source: preview.source,
            })}
          </p>

          {preview.records.length > 0 ? (
            <>
              <div className="table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>
                      {fields.map((key) => (
                        <th key={key}>{key}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.records.slice(0, 5).map((record, index) => (
                      <tr key={index}>
                        {fields.map((key) => (
                          <td key={key}>{String(record[key] ?? '')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <section className="live-field-mapping">
                <h4>{t('importPage.live.fieldMappingTitle')}</h4>
                <label htmlFor="live-x-field">{t('importPage.live.xField')}</label>
                <select
                  id="live-x-field"
                  className="input"
                  value={xField}
                  onChange={(event) => setXField(event.target.value)}
                >
                  {fields.map((key) => (
                    <option key={key} value={key}>
                      {key}
                    </option>
                  ))}
                </select>
                <label htmlFor="live-y-field">{t('importPage.live.yField')}</label>
                <select
                  id="live-y-field"
                  className="input"
                  value={yField}
                  onChange={(event) => setYField(event.target.value)}
                >
                  {fields.map((key) => (
                    <option key={key} value={key}>
                      {key}
                    </option>
                  ))}
                </select>
                <label htmlFor="live-series-field">{t('importPage.live.seriesField')}</label>
                <select
                  id="live-series-field"
                  className="input"
                  value={seriesField}
                  onChange={(event) => setSeriesField(event.target.value)}
                >
                  <option value="">{t('importPage.live.none')}</option>
                  {fields.map((key) => (
                    <option key={key} value={key}>
                      {key}
                    </option>
                  ))}
                </select>
                <h4>{t('importPage.live.fieldSelectionTitle')}</h4>
                <p className="hint">{t('importPage.live.fieldSelectionHint')}</p>
                <div className="table-wrap">
                  <table className="preview-table">
                    <thead>
                      <tr>
                        <th>{t('importPage.live.includeField')}</th>
                        <th>{t('importPage.live.sourceField')}</th>
                        <th>{t('importPage.live.outputField')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fields.map((key) => (
                        <tr key={key}>
                          <td>
                            <input
                              type="checkbox"
                              aria-label={`${t('importPage.live.includeField')} ${key}`}
                              checked={fieldMapping[key]?.include ?? true}
                              onChange={(event) =>
                                updateFieldMapping(key, { include: event.target.checked })
                              }
                            />
                          </td>
                          <td>{key}</td>
                          <td>
                            <input
                              className="input"
                              aria-label={`${t('importPage.live.renameField')} ${key}`}
                              value={fieldMapping[key]?.name ?? key}
                              onChange={(event) =>
                                updateFieldMapping(key, { name: event.target.value })
                              }
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          ) : (
            <p className="muted">{t('importPage.live.noRecords')}</p>
          )}
        </div>
      ) : null}

      <label htmlFor="live-name">{t('importPage.live.nameLabel')}</label>
      <input
        id="live-name"
        className="input"
        value={name}
        onChange={(event) => setName(event.target.value)}
      />

      <div className="import-actions">
        <button
          className="btn home-primary"
          type="button"
          onClick={handleImport}
          disabled={busy !== null}
        >
          {busy === 'import'
            ? t('importPage.live.importing')
            : t('importPage.live.import')}
        </button>
      </div>
    </section>
  )
}
