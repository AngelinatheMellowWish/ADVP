import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  importMultiFile,
  previewMultiFile,
  type MultiFilePayload,
  type MultiFilePreview,
} from '../api/importJobs'
import { errorMessage } from '../api/projects'

type MultiFileDialogProps = {
  projectId: string
  paths: string[]
  onClose: () => void
  onImported: (datasetId: string) => void
}

export function MultiFileDialog({
  projectId,
  paths,
  onClose,
  onImported,
}: MultiFileDialogProps) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'union' | 'join'>('union')
  const [leftKey, setLeftKey] = useState('')
  const [rightKey, setRightKey] = useState('')
  const [how, setHow] = useState<MultiFilePayload['how']>('inner')
  const [preview, setPreview] = useState<MultiFilePreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canJoin = paths.length === 2

  function payload(): MultiFilePayload {
    return {
      paths,
      mode,
      left_key: mode === 'join' ? leftKey.trim() : undefined,
      right_key: mode === 'join' ? rightKey.trim() : undefined,
      how: mode === 'join' ? how : undefined,
    }
  }

  async function handlePreview() {
    if (mode === 'join' && (!leftKey.trim() || !rightKey.trim())) {
      setError(t('importPage.multi.needsKeys'))
      return
    }
    setLoading(true)
    setError(null)
    try {
      setPreview(await previewMultiFile(projectId, payload()))
    } catch (caught) {
      setPreview(null)
      setError(`${t('importPage.multi.failed')} ${errorMessage(caught)}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleImport() {
    if (mode === 'join' && (!leftKey.trim() || !rightKey.trim())) {
      setError(t('importPage.multi.needsKeys'))
      return
    }
    setImporting(true)
    setError(null)
    try {
      const dataset = await importMultiFile(projectId, payload())
      onImported(dataset.id)
    } catch (caught) {
      setError(`${t('importPage.multi.failed')} ${errorMessage(caught)}`)
    } finally {
      setImporting(false)
    }
  }

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className="modal multi-file-modal"
        role="dialog"
        aria-modal="true"
        aria-label={t('importPage.multi.title')}
      >
        <h2>{t('importPage.multi.title')}</h2>

        <label htmlFor="multifile-mode">{t('importPage.multi.mode')}</label>
        <select
          id="multifile-mode"
          className="input"
          value={mode}
          onChange={(event) => {
            setMode(event.target.value === 'join' ? 'join' : 'union')
            setPreview(null)
          }}
        >
          <option value="union">{t('importPage.multi.union')}</option>
          <option value="join" disabled={!canJoin}>
            {t('importPage.multi.join')}
          </option>
        </select>

        {mode === 'join' ? (
          <div className="multi-file-keys">
            <label htmlFor="multifile-left-key">
              {t('importPage.multi.leftKey')}
              <input
                id="multifile-left-key"
                className="input"
                value={leftKey}
                onChange={(event) => setLeftKey(event.target.value)}
              />
            </label>
            <label htmlFor="multifile-right-key">
              {t('importPage.multi.rightKey')}
              <input
                id="multifile-right-key"
                className="input"
                value={rightKey}
                onChange={(event) => setRightKey(event.target.value)}
              />
            </label>
            <label htmlFor="multifile-how">
              {t('importPage.multi.how')}
              <select
                id="multifile-how"
                className="input"
                value={how}
                onChange={(event) =>
                  setHow(event.target.value as MultiFilePayload['how'])
                }
              >
                <option value="inner">{t('importPage.multi.hows.inner')}</option>
                <option value="left">{t('importPage.multi.hows.left')}</option>
                <option value="right">{t('importPage.multi.hows.right')}</option>
                <option value="full">{t('importPage.multi.hows.full')}</option>
              </select>
            </label>
          </div>
        ) : null}

        {preview ? (
          <div className="multi-file-preview">
            <dl className="stat-grid">
              <div>
                <dt>{t('importPage.multi.resultRows')}</dt>
                <dd>{preview.result_rows}</dd>
              </div>
              {preview.match_rate !== null ? (
                <div>
                  <dt>{t('importPage.multi.matchRate')}</dt>
                  <dd>{Math.round(preview.match_rate * 100)}%</dd>
                </div>
              ) : null}
              {preview.left_rows !== null ? (
                <div>
                  <dt>{t('importPage.multi.leftRows')}</dt>
                  <dd>{preview.left_rows}</dd>
                </div>
              ) : null}
              {preview.right_rows !== null ? (
                <div>
                  <dt>{t('importPage.multi.rightRows')}</dt>
                  <dd>{preview.right_rows}</dd>
                </div>
              ) : null}
              {preview.duplicate_keys ? (
                <div>
                  <dt>{t('importPage.multi.duplicateKeys')}</dt>
                  <dd>
                    {preview.duplicate_keys.left} / {preview.duplicate_keys.right}
                  </dd>
                </div>
              ) : null}
              <div>
                <dt>{t('importPage.multi.conflicts')}</dt>
                <dd>{preview.conflicts.join(', ') || t('importPage.multi.none')}</dd>
              </div>
            </dl>
            <div className="table-wrap">
              <table className="preview-table">
                <thead>
                  <tr>
                    {preview.columns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.preview.slice(0, 8).map((row, index) => (
                    <tr key={index}>
                      {preview.columns.map((column) => (
                        <td key={column}>{String(row[column] ?? '')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {error ? (
          <p className="error-text" role="alert">
            {error}
          </p>
        ) : null}

        <div className="modal-actions">
          <button className="btn" type="button" onClick={onClose} disabled={importing}>
            {t('importPage.multi.close')}
          </button>
          <button className="btn" type="button" onClick={handlePreview} disabled={loading}>
            {loading ? t('importPage.multi.previewing') : t('importPage.multi.preview')}
          </button>
          <button
            className="btn home-primary"
            type="button"
            onClick={handleImport}
            disabled={importing}
          >
            {t('importPage.multi.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}
