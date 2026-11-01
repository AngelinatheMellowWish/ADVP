export type PipelineEvent = {
  id: string
  run_id: string
  seq: number
  type: string
  payload: Record<string, unknown>
  created_at: string | null
}

export const PIPELINE_EVENT_TYPES = [
  'run_started',
  'step_started',
  'step_succeeded',
  'step_failed',
  'run_failed',
  'run_succeeded',
  'run_paused',
  'run_cancelled',
] as const

export type PipelineEventType = (typeof PIPELINE_EVENT_TYPES)[number]

export function subscribePipelineEvents(
  runId: string,
  since: number,
  onEvent: (event: PipelineEvent) => void,
  onError?: () => void,
): () => void {
  if (typeof EventSource === 'undefined') {
    return () => undefined
  }
  const source = new EventSource(
    `/api/pipeline-runs/${encodeURIComponent(runId)}/events?since=${Math.max(0, since)}`,
  )
  const listeners: { type: string; listener: EventListener }[] = []

  for (const type of PIPELINE_EVENT_TYPES) {
    const listener = ((event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as PipelineEvent
        if (typeof payload.seq === 'number') onEvent(payload)
      } catch {
        // Ignore malformed frames; the next replay or poll recovers state.
      }
    }) as EventListener
    source.addEventListener(type, listener)
    listeners.push({ type, listener })
  }

  source.onerror = () => {
    onError?.()
  }

  return () => {
    for (const { type, listener } of listeners) {
      source.removeEventListener(type, listener)
    }
    source.close()
  }
}
