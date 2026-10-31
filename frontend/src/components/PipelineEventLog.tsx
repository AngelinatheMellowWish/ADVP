import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { PipelineEvent } from '../api/pipelineEvents'

type EventLevel = 'info' | 'warning' | 'error'

const FILTERS: ('all' | EventLevel)[] = ['all', 'info', 'warning', 'error']

function eventLevel(type: string): EventLevel {
  if (type === 'step_failed' || type === 'run_failed') return 'error'
  if (type === 'run_paused' || type === 'run_cancelled') return 'warning'
  return 'info'
}

function summary(event: PipelineEvent): string {
  const payload = event.payload
  const key = typeof payload.key === 'string' ? payload.key : null
  const duration = typeof payload.duration_ms === 'number' ? payload.duration_ms : null
  const attempt = typeof payload.attempt === 'number' ? payload.attempt : null
  const error = typeof payload.error === 'string' ? payload.error : null
  const parts: string[] = []
  if (key) parts.push(key)
  if (attempt !== null) parts.push(`#${attempt}`)
  if (duration !== null) parts.push(`${duration}ms`)
  if (error) parts.push(error)
  return parts.join(' · ')
}

export function PipelineEventLog({ events }: { events: PipelineEvent[] }) {
  const { t } = useTranslation()
  const [filter, setFilter] = useState<'all' | EventLevel>('all')

  const visible = useMemo(
    () =>
      events.filter((event) => filter === 'all' || eventLevel(event.type) === filter),
    [events, filter],
  )

  return (
    <section className="card pipeline-event-card" aria-label={t('pipelinePage.events')}>
      <div className="pipeline-event-head">
        <h2>{t('pipelinePage.events')}</h2>
        <div className="pipeline-event-filters" role="group" aria-label={t('pipelinePage.filter')}>
          {FILTERS.map((item) => (
            <button
              key={item}
              type="button"
              className={filter === item ? 'btn active' : 'btn'}
              aria-pressed={filter === item}
              onClick={() => setFilter(item)}
            >
              {t(`pipelinePage.levels.${item}`)}
            </button>
          ))}
        </div>
      </div>
      {visible.length === 0 ? (
        <p className="muted">{t('pipelinePage.emptyEvents')}</p>
      ) : (
        <ol className="pipeline-event-log" data-testid="pipeline-event-log">
          {visible.map((event) => {
            const level = eventLevel(event.type)
            return (
              <li key={event.seq} className={`pipeline-event event-${level}`}>
                <span className="pipeline-event-seq">#{event.seq}</span>
                <span className={`pipeline-event-type event-type-${level}`}>
                  {t(`pipelinePage.eventTypes.${event.type}`, {
                    defaultValue: event.type,
                  })}
                </span>
                <span className="pipeline-event-summary">{summary(event)}</span>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}
