import { useTranslation } from 'react-i18next'

import type { SystemStatus } from '../api/system'

type SystemStatusCardProps = {
  status: SystemStatus | null
  loading: boolean
  error: string | null
  onRetry: () => void
}

type Tone = 'ok' | 'warning' | 'error' | 'unknown' | 'neutral'

const TONE_RANK: Record<Tone, number> = {
  neutral: 0,
  ok: 1,
  unknown: 2,
  warning: 3,
  error: 4,
}

function toneOf(value: string | undefined): Tone {
  if (!value) return 'unknown'
  if (value === 'ok' || value === 'online') return 'ok'
  if (value === 'degraded' || value === 'software') return 'warning'
  if (value === 'error' || value === 'offline') return 'error'
  return 'neutral'
}

function worstTone(rows: { tone: Tone }[]): Tone {
  return rows.reduce<Tone>(
    (worst, row) => (TONE_RANK[row.tone] > TONE_RANK[worst] ? row.tone : worst),
    'neutral',
  )
}

function formatNumber(value: number | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)
}

export function SystemStatusCard({
  status,
  loading,
  error,
  onRetry,
}: SystemStatusCardProps) {
  const { t } = useTranslation()

  function valueLabel(value: string | undefined): string {
    if (!value) return t('home.systemStatus.unknown')
    if (value === 'ok') return t('home.systemStatus.values.ok')
    if (value === 'software') return t('home.systemStatus.values.software')
    if (value === 'degraded') return t('home.systemStatus.values.degraded')
    if (value === 'error') return t('home.systemStatus.values.error')
    if (value === 'unavailable') return t('home.systemStatus.values.unavailable')
    return value
  }

  const rows: { key: string; label: string; value: string; tone: Tone }[] = status
    ? [
        {
          key: 'service',
          label: t('home.systemStatus.service'),
          value: valueLabel(status.service),
          tone: toneOf(status.service),
        },
        {
          key: 'provider',
          label: t('home.systemStatus.provider'),
          value: valueLabel(status.provider),
          tone: toneOf(status.provider),
        },
        {
          key: 'gpu',
          label: t('home.systemStatus.gpu'),
          value: valueLabel(status.gpu),
          tone: toneOf(status.gpu),
        },
        {
          key: 'disk',
          label: t('home.systemStatus.disk'),
          value:
            formatNumber(status.disk_free_gb) === null
              ? t('home.systemStatus.unknown')
              : t('home.systemStatus.diskValue', {
                  value: formatNumber(status.disk_free_gb),
                }),
          tone: formatNumber(status.disk_free_gb) === null ? 'unknown' : 'neutral',
        },
        {
          key: 'database',
          label: t('home.systemStatus.database'),
          value: valueLabel(status.database),
          tone: toneOf(status.database),
        },
        {
          key: 'cpu',
          label: t('home.systemStatus.cpu'),
          value:
            formatNumber(status.cpu_percent) === null
              ? t('home.systemStatus.unknown')
              : `${formatNumber(status.cpu_percent)}%`,
          tone: formatNumber(status.cpu_percent) === null ? 'unknown' : 'neutral',
        },
        {
          key: 'memory',
          label: t('home.systemStatus.memory'),
          value:
            formatNumber(status.memory_percent) === null
              ? t('home.systemStatus.unknown')
              : `${formatNumber(status.memory_percent)}%`,
          tone: formatNumber(status.memory_percent) === null ? 'unknown' : 'neutral',
        },
        {
          key: 'network',
          label: t('home.systemStatus.network'),
          value:
            status.network_online === true
              ? t('home.systemStatus.online')
              : status.network_online === false
                ? t('home.systemStatus.offline')
                : t('home.systemStatus.unknown'),
          tone:
            status.network_online === true
              ? 'ok'
              : status.network_online === false
                ? 'error'
                : 'unknown',
        },
      ]
    : []

  const unavailable = !loading && (!status || error)
  const overallTone = worstTone(rows)
  const overallLabel =
    overallTone === 'warning'
      ? t('home.systemStatus.values.degraded')
      : overallTone === 'error'
        ? t('home.systemStatus.values.error')
        : overallTone === 'unknown'
          ? t('home.systemStatus.unknown')
          : t('home.systemStatus.values.ok')
  const overallPillTone =
    overallTone === 'ok'
      ? 'ok'
      : overallTone === 'warning' || overallTone === 'error'
        ? overallTone
        : 'muted'

  return (
    <section
      className="card system-status"
      aria-labelledby="system-status-title"
      data-testid="system-status-card"
    >
      <div className="home-section-head">
        <h2 id="system-status-title">{t('home.systemStatus.title')}</h2>
        {unavailable ? (
          <span className="status-pill status-pill-warning">
            {t('home.systemStatus.unavailable')}
          </span>
        ) : status ? (
          <span
            className={`status-pill status-pill-${overallPillTone}`}
            data-testid="system-status-overall"
          >
            {overallLabel}
          </span>
        ) : null}
      </div>
      {loading ? (
        <p className="muted" role="status">
          {t('home.systemStatus.loading')}
        </p>
      ) : unavailable ? (
        <div className="system-status-unavailable">
          <p className="muted">{t('home.systemStatus.unavailableHint')}</p>
          {error ? <p className="home-hint">{error}</p> : null}
          <button className="btn" type="button" onClick={onRetry}>
            {t('home.systemStatus.retry')}
          </button>
        </div>
      ) : (
        <dl className="status-list">
          {rows.map((row) => (
            <div className="status-row" key={row.key}>
              <dt>{row.label}</dt>
              <dd className={`status-value status-value-${row.tone}`}>{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}
