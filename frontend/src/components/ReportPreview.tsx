import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  previewPipelineReport,
  type ReportRegenerateInput,
} from '../api/pipelines'

type ReportPreviewProps = {
  runId: string
  draft: ReportRegenerateInput
}

export function ReportPreview({ runId, draft }: ReportPreviewProps) {
  const { t } = useTranslation()
  const [html, setHtml] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(() => {
      previewPipelineReport(runId, draft)
        .then((content) => {
          if (cancelled) return
          setHtml(content)
          setError(null)
        })
        .catch((caught: unknown) => {
          if (cancelled) return
          setHtml('')
          setError(caught instanceof Error ? caught.message : String(caught))
        })
    }, 500)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [draft, runId, attempt])

  if (error) {
    return (
      <div className="report-preview-error">
        <p className="error-text" role="alert">
          {t('reportPage.previewFailed', { message: error })}
        </p>
        <button className="btn" type="button" onClick={() => setAttempt((value) => value + 1)}>
          {t('reportPage.previewRetry')}
        </button>
      </div>
    )
  }

  if (!html) {
    return <p className="muted">{t('reportPage.previewLoading')}</p>
  }

  return (
    <iframe
      className="report-preview-frame"
      data-testid="report-html-preview"
      title={t('reportPage.preview')}
      sandbox=""
      srcDoc={html}
    />
  )
}
