import { useState } from 'react'

import {
  enhanceTextStats,
  errorMessage,
  importDocument,
  importKafka,
  importRemote,
  importTextStats,
  importWeb,
  importWebSocket,
  inspectDocument,
  inspectWeb,
  previewKafka,
  previewWebSocket,
  type DocumentTableInfo,
  type StreamPreviewResponse,
  type TextFact,
  type TextStatsExtraction,
  type WebTableInfo,
} from '../api/projects'
import { TextStatsCandidates } from './TextStatsCandidates'

type Candidate = {
  index: number
  row_count: number
  column_count: number
  confidence: number
  headers: string[]
  preview: string[][]
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function CandidateList({
  tables,
  onImport,
  busy,
  emptyText = '没有候选表格。',
}: {
  tables: Candidate[]
  onImport: (table: Candidate) => void
  busy: boolean
  emptyText?: string
}) {
  if (tables.length === 0) return <p className="muted">{emptyText}</p>
  return (
    <div className="candidate-list">
      {tables.map((table) => (
        <article className="candidate" key={table.index}>
          <div className="panel-title">
            <div>
              <strong>表格 #{table.index}</strong>
              <p className="muted">
                {table.row_count} 行 × {table.column_count} 列 · 置信度{' '}
                {(table.confidence * 100).toFixed(0)}%
              </p>
            </div>
            <button
              className="button"
              type="button"
              onClick={() => onImport(table)}
              disabled={busy}
            >
              导入此表
            </button>
          </div>
          {table.preview.length > 0 ? (
            <div className="table-wrap">
              <table className="preview-table">
                <thead>
                  <tr>
                    {table.headers.map((header) => (
                      <th key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.preview.slice(0, 3).map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {table.headers.map((_, columnIndex) => (
                        <td key={columnIndex}>{renderValue(row[columnIndex])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </article>
      ))}
    </div>
  )
}

function StreamPreview({ preview }: { preview: StreamPreviewResponse }) {
  if (preview.records.length === 0) return <p className="muted">没有收到消息。</p>
  return (
    <div>
      <p className="muted">
        {preview.source} · {preview.count} 条消息
      </p>
      <pre className="json-preview">
        {JSON.stringify(preview.records.slice(0, 3), null, 2)}
      </pre>
    </div>
  )
}

export function MoreSourcesPanel({
  projectId,
  onImported,
}: {
  projectId: string
  onImported: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [remoteUrl, setRemoteUrl] = useState('')
  const [remoteName, setRemoteName] = useState('')
  const [remoteToken, setRemoteToken] = useState('')

  const [docPath, setDocPath] = useState('')
  const [docName, setDocName] = useState('')
  const [docTables, setDocTables] = useState<DocumentTableInfo[]>([])
  const [docText, setDocText] = useState<TextStatsExtraction | null>(null)
  const [docSha256, setDocSha256] = useState('')
  const [docAI, setDocAI] = useState<Record<string, unknown> | null>(null)
  const [docMessage, setDocMessage] = useState<string | null>(null)

  const [webUrl, setWebUrl] = useState('')
  const [webName, setWebName] = useState('')
  const [webTables, setWebTables] = useState<WebTableInfo[]>([])

  const [streamMode, setStreamMode] = useState<'websocket' | 'kafka'>('websocket')
  const [wsUrl, setWsUrl] = useState('')
  const [kafkaBootstrap, setKafkaBootstrap] = useState('')
  const [kafkaTopic, setKafkaTopic] = useState('')
  const [streamName, setStreamName] = useState('')
  const [maxMessages, setMaxMessages] = useState('50')
  const [streamTimeout, setStreamTimeout] = useState('10')
  const [streamPreview, setStreamPreview] = useState<StreamPreviewResponse | null>(null)

  async function execute(
    action: () => Promise<{ name: string; row_count: number }>,
    label: string,
  ) {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const dataset = await action()
      setMessage(`${label}：${dataset.name}（${dataset.row_count} 行）`)
      await onImported()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleDocumentInspect() {
    const path = docPath.trim()
    if (!path) return
    setError(null)
    setMessage(null)
    setDocTables([])
    setDocText(null)
    setDocSha256('')
    setDocAI(null)
    if (!/\.(pdf|docx|txt|md|rtf|html?)$/i.test(path)) {
      setDocMessage(
        '仅支持 PDF、DOCX、TXT、Markdown、RTF 或 HTML 文件；请检查路径与后缀。扫描件与图片不做 OCR。',
      )
      return
    }
    setBusy(true)
    try {
      const result = await inspectDocument(projectId, path)
      setDocTables(result.tables)
      setDocText(result.text ?? null)
      setDocSha256(result.source_sha256 ?? '')
      const factCount = result.text?.long.facts.length ?? 0
      if (result.tables.length > 0) {
        setDocMessage(`发现 ${result.tables.length} 个候选表格（${result.format}）`)
      } else if (factCount > 0) {
        setDocMessage(
          `未发现表格，发现 ${factCount} 条文本统计候选（${result.format}）。请勾选、编辑后确认导入。`,
        )
      } else {
        setDocMessage(
          '未发现表格，也没有识别到数字统计事实。支持本地 PDF（文本层）、DOCX、TXT、Markdown、RTF 与 HTML 正文；不支持扫描件与图片（无 OCR）。',
        )
      }
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleTextStatsImport(shape: 'long' | 'wide', facts: TextFact[]) {
    if (!docSha256) {
      setError('检查文档后才能导入文本统计，请重新检查文件。')
      return
    }
    await execute(
      () =>
        importTextStats(
          projectId,
          docPath.trim(),
          docSha256,
          shape,
          facts,
          docName.trim() || undefined,
          docAI,
        ),
      shape === 'wide' ? '文本统计宽表导入' : '文本统计长表导入',
    )
  }

  async function handleTextStatsAI(facts: TextFact[]) {
    if (!docSha256 || !docText) {
      setError('检查文档后才能执行 AI 增强，请重新检查文件。')
      return
    }
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await enhanceTextStats(projectId, docPath.trim(), docSha256, facts)
      setDocText({
        ...docText,
        long: { ...docText.long, facts: result.facts, warnings: result.warnings },
        wide: { ...docText.wide, warnings: result.warnings },
      })
      const ai = result.ai as { used?: boolean; model?: string | null }
      setDocAI(ai.used ? result.ai : null)
      setMessage(
        ai.used
          ? `AI 增强完成（${ai.model ?? '未知模型'}）；请人工复核后再导入。`
          : 'AI 增强失败，已保留本地规则结果；可继续编辑或直接导入。',
      )
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleWebInspect() {
    if (!webUrl.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await inspectWeb(projectId, webUrl.trim())
      setWebTables(result.tables)
      setMessage(`发现 ${result.tables.length} 个 HTML 表格`)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  function streamParameters(): { messages: number; timeout: number } {
    const messages = Number(maxMessages)
    const timeout = Number(streamTimeout)
    return {
      messages: Number.isFinite(messages) && messages > 0 ? messages : 50,
      timeout: Number.isFinite(timeout) && timeout > 0 ? timeout : 10,
    }
  }

  async function handleStreamPreview() {
    const { messages, timeout } = streamParameters()
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      if (streamMode === 'websocket') {
        setStreamPreview(await previewWebSocket(wsUrl.trim(), messages, timeout))
      } else {
        setStreamPreview(
          await previewKafka(kafkaBootstrap.trim(), kafkaTopic.trim(), messages, timeout),
        )
      }
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleStreamImport() {
    const { messages, timeout } = streamParameters()
    if (streamMode === 'websocket') {
      await execute(
        () => importWebSocket(projectId, wsUrl.trim(), streamName.trim(), messages, timeout),
        'WebSocket 导入',
      )
    } else {
      await execute(
        () =>
          importKafka(
            projectId,
            kafkaBootstrap.trim(),
            kafkaTopic.trim(),
            streamName.trim(),
            messages,
            timeout,
          ),
        'Kafka 导入',
      )
    }
  }

  return (
    <section className="panel">
      <h3>更多数据源</h3>
      <p className="muted">
        远程文件、PDF/Word 表格、文本统计、网页表格、WebSocket 与 Kafka。凭据仅用于本次请求，
        不写入工程。
      </p>
      {message ? <p className="muted">{message}</p> : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      <details className="advanced-options">
        <summary>远程 URL 文件（HTTP/HTTPS）</summary>
        <div className="stack-form">
          <input
            aria-label="远程 URL"
            placeholder="https://example.com/data.csv"
            value={remoteUrl}
            onChange={(event) => setRemoteUrl(event.target.value)}
          />
          <input
            aria-label="远程数据集名称"
            placeholder="数据集名称（可选）"
            value={remoteName}
            onChange={(event) => setRemoteName(event.target.value)}
          />
          <input
            aria-label="远程 Bearer Token"
            placeholder="Bearer Token（可选，不保存）"
            value={remoteToken}
            onChange={(event) => setRemoteToken(event.target.value)}
          />
          <button
            className="button"
            type="button"
            disabled={busy || !remoteUrl.trim()}
            onClick={() =>
              void execute(
                () =>
                  importRemote(
                    projectId,
                    remoteUrl.trim(),
                    remoteName.trim(),
                    remoteToken.trim() || undefined,
                  ),
                '远程导入',
              )
            }
          >
            下载并导入
          </button>
        </div>
      </details>

      <details className="advanced-options">
        <summary>文档 / 文本统计</summary>
        <div className="stack-form">
          <input
            aria-label="文档路径"
            placeholder="本地 PDF/DOCX/TXT/MD/RTF/HTML 绝对路径"
            value={docPath}
            onChange={(event) => {
              setDocPath(event.target.value)
              setDocTables([])
              setDocText(null)
              setDocSha256('')
              setDocAI(null)
              setDocMessage(null)
            }}
          />
          <input
            aria-label="文档数据集名称"
            placeholder="数据集名称（可选）"
            value={docName}
            onChange={(event) => setDocName(event.target.value)}
          />
          <button
            className="button"
            type="button"
            disabled={busy || !docPath.trim()}
            onClick={() => void handleDocumentInspect()}
          >
            提取候选表格
          </button>
        </div>
        <p className="muted">
          请输入本机绝对路径（如 C:\data\report.docx），浏览器无法直接选择本地文件。支持
          PDF（文本层）/DOCX 表格与 TXT/MD/RTF/HTML 正文统计；扫描件与图片不做 OCR。
        </p>
        {docMessage ? (
          <p className={docTables.length > 0 ? 'muted' : 'warning'} role="status">
            {docMessage}
          </p>
        ) : null}
        <CandidateList
          tables={docTables}
          busy={busy}
          emptyText="没有可导入的表格。"
          onImport={(table) =>
            void execute(
              () =>
                importDocument(
                  projectId,
                  docPath.trim(),
                  table.index,
                  docName.trim() || undefined,
                ),
              '文档表格导入',
            )
          }
        />
        {docText && docText.long.facts.length > 0 ? (
          <TextStatsCandidates
            extraction={docText}
            busy={busy}
            onImport={handleTextStatsImport}
            onAIEnhance={handleTextStatsAI}
          />
        ) : null}
      </details>

      <details className="advanced-options">
        <summary>网页 HTML 表格（静态）</summary>
        <div className="stack-form">
          <input
            aria-label="网页 URL"
            placeholder="https://example.com/page"
            value={webUrl}
            onChange={(event) => {
              setWebUrl(event.target.value)
              setWebTables([])
            }}
          />
          <input
            aria-label="网页数据集名称"
            placeholder="数据集名称（可选）"
            value={webName}
            onChange={(event) => setWebName(event.target.value)}
          />
          <button
            className="button"
            type="button"
            disabled={busy || !webUrl.trim()}
            onClick={() => void handleWebInspect()}
          >
            提取网页表格
          </button>
        </div>
        <CandidateList
          tables={webTables}
          busy={busy}
          onImport={(table) =>
            void execute(
              () =>
                importWeb(
                  projectId,
                  webUrl.trim(),
                  table.index,
                  webName.trim() || undefined,
                ),
              '网页表格导入',
            )
          }
        />
      </details>

      <details className="advanced-options">
        <summary>实时流（WebSocket / Kafka）</summary>
        <div className="stack-form">
          <select
            aria-label="流协议"
            value={streamMode}
            onChange={(event) =>
              setStreamMode(event.target.value === 'kafka' ? 'kafka' : 'websocket')
            }
          >
            <option value="websocket">WebSocket</option>
            <option value="kafka">Kafka</option>
          </select>
          {streamMode === 'websocket' ? (
            <input
              aria-label="WebSocket URL"
              placeholder="ws://host:port/path"
              value={wsUrl}
              onChange={(event) => setWsUrl(event.target.value)}
            />
          ) : (
            <>
              <input
                aria-label="Kafka bootstrap"
                placeholder="host:port,host:port"
                value={kafkaBootstrap}
                onChange={(event) => setKafkaBootstrap(event.target.value)}
              />
              <input
                aria-label="Kafka topic"
                placeholder="topic"
                value={kafkaTopic}
                onChange={(event) => setKafkaTopic(event.target.value)}
              />
            </>
          )}
          <input
            aria-label="流数据集名称"
            placeholder="数据集名称（可选）"
            value={streamName}
            onChange={(event) => setStreamName(event.target.value)}
          />
          <input
            aria-label="最大消息数"
            type="number"
            min="1"
            max="1000"
            value={maxMessages}
            onChange={(event) => setMaxMessages(event.target.value)}
          />
          <input
            aria-label="流超时秒数"
            type="number"
            min="1"
            max="120"
            value={streamTimeout}
            onChange={(event) => setStreamTimeout(event.target.value)}
          />
          <div className="inline-form">
            <button
              className="button"
              type="button"
              disabled={
                busy ||
                (streamMode === 'websocket'
                  ? !wsUrl.trim()
                  : !kafkaBootstrap.trim() || !kafkaTopic.trim())
              }
              onClick={() => void handleStreamPreview()}
            >
              预览消息
            </button>
            <button
              className="button"
              type="button"
              disabled={
                busy ||
                (streamMode === 'websocket'
                  ? !wsUrl.trim()
                  : !kafkaBootstrap.trim() || !kafkaTopic.trim())
              }
              onClick={() => void handleStreamImport()}
            >
              导入窗口
            </button>
          </div>
        </div>
        {streamPreview ? <StreamPreview preview={streamPreview} /> : null}
      </details>
    </section>
  )
}
