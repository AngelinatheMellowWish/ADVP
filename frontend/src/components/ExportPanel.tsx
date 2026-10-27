import { useEffect, useState } from 'react'

import { errorMessage } from '../api/projects'

type ExportKind = 'html' | 'html-file' | 'pdf' | 'python' | 'notebook'

const EXTENSIONS: Record<ExportKind, string> = {
  html: 'zip',
  'html-file': 'html',
  pdf: 'pdf',
  python: 'py',
  notebook: 'ipynb',
}

export function ExportPanel({ selectionId }: { selectionId: string }) {
  const [busy, setBusy] = useState<ExportKind | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [manifest, setManifest] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch(`/api/chart-selections/${selectionId}/export/manifest`)
      .then(async (response) => {
        if (!response.ok) throw new Error('manifest unavailable')
        return (await response.json()) as Record<string, unknown>
      })
      .then((payload) => {
        if (!cancelled) setManifest(payload)
      })
      .catch(() => {
        if (!cancelled) setManifest(null)
      })
    return () => {
      cancelled = true
    }
  }, [selectionId])

  async function download(kind: ExportKind) {
    setBusy(kind)
    setError(null)
    setStatus(null)
    try {
      const response = await fetch(`/api/chart-selections/${selectionId}/export/${kind}`)
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as
          | { detail?: { message?: string } }
          | null
        throw new Error(payload?.detail?.message ?? `导出失败（HTTP ${response.status}）`)
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `advp-${selectionId}.${EXTENSIONS[kind]}`
      link.click()
      URL.revokeObjectURL(url)
      setStatus(`已导出 ${kind.toUpperCase()}`)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="export-panel">
      <div className="inline-form">
        <button className="button" onClick={() => void download('html')} disabled={busy !== null}>
          {busy === 'html' ? '打包中…' : '导出 HTML'}
        </button>
        <button
          className="button"
          onClick={() => void download('html-file')}
          disabled={busy !== null}
        >
          {busy === 'html-file' ? '内联中…' : '导出单文件 HTML'}
        </button>
        <button className="button" onClick={() => void download('pdf')} disabled={busy !== null}>
          {busy === 'pdf' ? '打印中…' : '导出 PDF'}
        </button>
        <button className="button" onClick={() => void download('python')} disabled={busy !== null}>
          {busy === 'python' ? '生成中…' : '导出 Python'}
        </button>
        <button
          className="button"
          onClick={() => void download('notebook')}
          disabled={busy !== null}
        >
          {busy === 'notebook' ? '生成中…' : '导出 Notebook'}
        </button>
      </div>
      {status ? <p className="notice">{status}</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {manifest ? (
        <details className="chart-dependent-details">
          <summary>导出 manifest</summary>
          <ul>
            <li>图表：{String(manifest.chart_id ?? '')}</li>
            <li>渲染器：{String(manifest.renderer ?? '')}</li>
            <li>模型：{String(manifest.model ?? '规则降级')}</li>
            <li>提示词：{String(manifest.prompt_version ?? '')}</li>
            <li>数据哈希：{String(manifest.source_sha256 ?? '').slice(0, 16)}…</li>
          </ul>
        </details>
      ) : null}
    </div>
  )
}
