import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'

import {
  createLiveSession,
  pauseLiveSession,
  resumeLiveSession,
  saveLiveSnapshot,
  stopLiveSession,
  type LiveSession,
  type LiveSessionInput,
} from '../api/live'
import { errorMessage } from '../api/projects'
import { EChartsFigure } from './EChartsFigure'

export function LiveStreamPanel({ projectId }: { projectId: string }) {
  const [kind, setKind] = useState<'websocket' | 'kafka'>('websocket')
  const [url, setUrl] = useState('')
  const [headerName, setHeaderName] = useState('')
  const [headerValue, setHeaderValue] = useState('')
  const [bootstrap, setBootstrap] = useState('')
  const [topic, setTopic] = useState('')
  const [group, setGroup] = useState('')
  const [securityProtocol, setSecurityProtocol] = useState('')
  const [saslMechanism, setSaslMechanism] = useState('')
  const [saslUsername, setSaslUsername] = useState('')
  const [saslPassword, setSaslPassword] = useState('')
  const [sslCa, setSslCa] = useState('')
  const [sampleInterval, setSampleInterval] = useState(0)
  const [session, setSession] = useState<LiveSession | null>(null)
  const [xField, setXField] = useState('')
  const [yField, setYField] = useState('')
  const [seriesField, setSeriesField] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const fields = useMemo(() => detectFields(session?.records ?? []), [session?.records])
  const effectiveX = xField || fields.x
  const effectiveY = yField || fields.y
  const option = useMemo(
    () =>
      buildLiveOption(
        session?.records ?? [],
        effectiveX,
        effectiveY,
        seriesField || fields.series,
      ),
    [session?.records, effectiveX, effectiveY, seriesField, fields.series],
  )

  const sessionId = session?.session_id
  const lastSequence = useRef(0)
  const statusRef = useRef<string | undefined>(session?.status)
  statusRef.current = session?.status
  const [reconnectKey, setReconnectKey] = useState(0)
  useEffect(() => {
    if (!sessionId) return
    if (typeof window === 'undefined' || typeof window.EventSource === 'undefined') return
    let reconnectTimer: number | null = null
    const source = new window.EventSource(
      `/api/streams/live/${sessionId}/events?since=${lastSequence.current}`,
    )
    source.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as LiveSession & {
          reset?: boolean
          to_sequence?: number
        }
        const incoming = payload.records ?? []
        setSession((current) => {
          const base = payload.reset || !current ? [] : current.records
          const records = [...base, ...incoming].slice(-1000)
          return {
            ...(current ?? payload),
            ...payload,
            records,
            count: records.length,
          }
        })
        lastSequence.current = payload.to_sequence ?? payload.sequence ?? lastSequence.current
      } catch {
        setError('实时消息解析失败')
      }
    }
    source.onerror = () => {
      if (statusRef.current === 'stopped') return
      setSession((current) =>
        current ? { ...current, status: 'reconnecting' } : current,
      )
      source.close()
      reconnectTimer = window.setTimeout(() => setReconnectKey((value) => value + 1), 1000)
    }
    return () => {
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      source.close()
    }
  }, [sessionId, reconnectKey])

  async function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const input = buildInput()
      const created = await createLiveSession(input)
      setSession(created)
      setXField('')
      setYField('')
      setSeriesField('')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  function buildInput(): LiveSessionInput {
    if (kind === 'websocket') {
      const headers: Record<string, string> = {}
      if (headerName.trim() && headerValue.trim()) headers[headerName.trim()] = headerValue.trim()
      return {
        kind,
        url: url.trim(),
        headers,
        max_messages: 1000,
        sample_interval_ms: sampleInterval,
      }
    }
    return {
      kind,
      bootstrap: bootstrap.trim(),
      topic: topic.trim(),
      group: group.trim() || undefined,
      auto_offset_reset: 'latest',
      security_protocol: securityProtocol.trim() || undefined,
      sasl_mechanism: saslMechanism.trim() || undefined,
      sasl_username: saslUsername.trim() || undefined,
      sasl_password: saslPassword || undefined,
      ssl_ca_location: sslCa.trim() || undefined,
      max_messages: 1000,
      sample_interval_ms: sampleInterval,
    }
  }

  async function control(action: 'pause' | 'resume' | 'stop') {
    if (!session) return
    setBusy(true)
    setError(null)
    try {
      const updated =
        action === 'pause'
          ? await pauseLiveSession(session.session_id)
          : action === 'resume'
            ? await resumeLiveSession(session.session_id)
            : await stopLiveSession(session.session_id)
      setSession(updated)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function saveSnapshot() {
    if (!session) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const dataset = await saveLiveSnapshot(session.session_id, projectId)
      setMessage(`已保存窗口：${dataset.name}（${dataset.row_count} 行）`)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const fieldOptions = fields.keys

  return (
    <section className="panel live-panel" aria-label="实时流">
      <div className="panel-title">
        <div>
          <h3>实时流图表</h3>
          <p className="muted">
            服务端持有 WebSocket/Kafka 连接与有界缓冲；前端通过 SSE 接收滑动窗口。
          </p>
        </div>
        {session ? (
          <span className={`badge live-status ${session.status}`}>{session.status}</span>
        ) : null}
      </div>

      {!session ? (
        <form onSubmit={start} className="stack-form">
          <label>
            来源
            <select value={kind} onChange={(event) => setKind(event.target.value as 'websocket' | 'kafka')}>
              <option value="websocket">WebSocket</option>
              <option value="kafka">Kafka</option>
            </select>
          </label>
          {kind === 'websocket' ? (
            <>
              <input
                aria-label="WebSocket URL"
                placeholder="ws://127.0.0.1:9000/stream"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
              />
              <div className="inline-form">
                <input
                  aria-label="请求头名称"
                  placeholder="请求头名称（可选）"
                  value={headerName}
                  onChange={(event) => setHeaderName(event.target.value)}
                />
                <input
                  aria-label="请求头值"
                  placeholder="请求头值（可选）"
                  value={headerValue}
                  onChange={(event) => setHeaderValue(event.target.value)}
                />
              </div>
            </>
          ) : (
            <>
              <input
                aria-label="Kafka bootstrap"
                placeholder="bootstrap，例如 127.0.0.1:9092"
                value={bootstrap}
                onChange={(event) => setBootstrap(event.target.value)}
              />
              <input
                aria-label="Kafka topic"
                placeholder="topic"
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
              />
              <input
                aria-label="Kafka group"
                placeholder="consumer group（可选）"
                value={group}
                onChange={(event) => setGroup(event.target.value)}
              />
              <input
                aria-label="Kafka security protocol"
                placeholder="security protocol（可选）"
                value={securityProtocol}
                onChange={(event) => setSecurityProtocol(event.target.value)}
              />
              <input
                aria-label="Kafka SASL mechanism"
                placeholder="SASL mechanism（可选）"
                value={saslMechanism}
                onChange={(event) => setSaslMechanism(event.target.value)}
              />
              <input
                aria-label="Kafka SASL username"
                placeholder="SASL username（可选）"
                value={saslUsername}
                onChange={(event) => setSaslUsername(event.target.value)}
              />
              <input
                aria-label="Kafka SASL password"
                type="password"
                placeholder="SASL password（可选，仅会话内存）"
                value={saslPassword}
                onChange={(event) => setSaslPassword(event.target.value)}
              />
              <input
                aria-label="Kafka SSL CA"
                placeholder="SSL CA 路径（可选）"
                value={sslCa}
                onChange={(event) => setSslCa(event.target.value)}
              />
            </>
          )}
          <label>
            采样间隔（ms，0 表示不降频）
            <input
              type="number"
              min="0"
              max="60000"
              value={sampleInterval}
              onChange={(event) => setSampleInterval(Number(event.target.value))}
            />
          </label>
          <button
            className="button"
            type="submit"
            disabled={busy || (kind === 'websocket' ? !url.trim() : !bootstrap.trim() || !topic.trim())}
          >
            {busy ? '连接中…' : '开始实时'}
          </button>
        </form>
      ) : (
        <>
          <div className="chart-controls">
            <button className="button" onClick={() => void control(session.paused ? 'resume' : 'pause')} disabled={busy}>
              {session.paused ? '恢复' : '暂停'}
            </button>
            <button className="button" onClick={() => void control('stop')} disabled={busy}>
              停止
            </button>
            <button className="button" onClick={() => void saveSnapshot()} disabled={busy || session.count === 0}>
              保存当前窗口
            </button>
            <span className="muted">
              {session.count} 条 · 序号 {session.sequence}
              {session.error ? ` · ${session.error}` : ''}
            </span>
          </div>
          <div className="chart-selection-controls">
            <label>
              X 字段
              <select value={effectiveX} onChange={(event) => setXField(event.target.value)}>
                {fieldOptions.map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Y 字段
              <select value={effectiveY} onChange={(event) => setYField(event.target.value)}>
                {fieldOptions.map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
            </label>
            <label>
              系列
              <select value={seriesField} onChange={(event) => setSeriesField(event.target.value)}>
                <option value="">无</option>
                {fieldOptions.map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {message ? <p className="notice">{message}</p> : null}
          {session.status === 'reconnecting' ? (
            <p className="notice">连接中断，正在自动重连；当前窗口保留。</p>
          ) : null}
          {session.records.length > 0 ? (
            <EChartsFigure option={option} selectionId={session.session_id} />
          ) : (
            <p className="muted">等待首条消息…</p>
          )}
        </>
      )}
      {error ? <p className="error">{error}</p> : null}
    </section>
  )
}

function detectFields(records: Record<string, unknown>[]) {
  const keys = Array.from(new Set(records.flatMap((record) => Object.keys(record))))
  const x =
    keys.find((key) => /time|timestamp|ts|date/i.test(key)) ??
    keys.find((key) => typeof records[0]?.[key] === 'string') ??
    keys[0] ??
    ''
  const y =
    keys.find((key) => key !== x && typeof records[0]?.[key] === 'number') ??
    keys.find((key) => key !== x) ??
    ''
  const series = keys.find(
    (key) => key !== x && key !== y && typeof records[0]?.[key] === 'string',
  )
  return { keys, x, y, series }
}

function buildLiveOption(
  records: Record<string, unknown>[],
  xField: string,
  yField: string,
  seriesField: string | undefined,
): Record<string, unknown> {
  const points = records.slice(-500)
  const categories = points.map((record) => String(record[xField] ?? ''))
  const groups = new Map<string, (number | null)[]>()
  for (const record of points) {
    const key = seriesField ? String(record[seriesField] ?? 'value') : 'value'
    const value = Number(record[yField])
    const values = groups.get(key) ?? []
    values.push(Number.isFinite(value) ? value : null)
    groups.set(key, values)
  }
  return {
    title: { text: '实时窗口' },
    tooltip: { trigger: 'axis' },
    grid: { left: 56, right: 24, top: 48, bottom: 48 },
    xAxis: { type: 'category', data: categories, axisLabel: { hideOverlap: true } },
    yAxis: { type: 'value' },
    dataZoom: [{ type: 'inside' }],
    series: Array.from(groups.entries()).map(([name, data]) => ({
      name,
      type: 'line',
      showSymbol: false,
      animation: false,
      data,
    })),
  }
}
