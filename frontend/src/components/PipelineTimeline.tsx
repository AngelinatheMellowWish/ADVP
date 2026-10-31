import { useTranslation } from 'react-i18next'

export type TimelineStep = {
  key: string
  status: string
  name?: string
  attempts?: number
}

export function PipelineTimeline({
  steps,
  activeKey,
  onSelect,
}: {
  steps: TimelineStep[]
  activeKey: string | null
  onSelect: (key: string) => void
}) {
  const { t } = useTranslation()

  return (
    <ol className="pipeline-timeline" aria-label={t('pipelinePage.timeline')}>
      {steps.map((step) => (
        <li key={step.key}>
          <button
            className={
              step.key === activeKey ? 'pipeline-step active' : 'pipeline-step'
            }
            type="button"
            data-testid={`step-${step.key}`}
            data-status={step.status}
            aria-current={step.key === activeKey ? 'step' : undefined}
            onClick={() => onSelect(step.key)}
          >
            <span className="pipeline-step-name">
              {step.name ?? t(`pipelinePage.steps.${step.key}`)}
            </span>
            <span className={`pipeline-step-status status-${step.status}`}>
              {t(`pipelinePage.status.${step.status}`, {
                defaultValue: step.status,
              })}
            </span>
            {typeof step.attempts === 'number' && step.attempts > 1 ? (
              <span className="pipeline-step-attempts">
                {t('pipelinePage.attempts', { count: step.attempts })}
              </span>
            ) : null}
          </button>
        </li>
      ))}
    </ol>
  )
}
