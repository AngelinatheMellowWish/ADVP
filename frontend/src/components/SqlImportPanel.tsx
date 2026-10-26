import { useState, type FormEvent } from 'react'

import {
  errorMessage,
  importSqlDataset,
  listSqlTables,
  previewSql,
  testSqlConnection,
  type SqlPreviewResponse,
  type SqlTableInfo,
} from '../api/projects'

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function SqlPreviewTable({ preview }: { preview: SqlPreviewResponse }) {
  const columns = preview.columns.map((column) => column.name)
  if (columns.length === 0) return <p className="muted">没有可预览的列。</p>
  return (
    <div className="table-wrap">
      <table className="preview-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {preview.rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length}>查询没有返回行。</td>
            </tr>
          ) : (
            preview.rows.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td key={column}>{renderValue(row[column])}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

export function SqlImportPanel({
  projectId,
  onImported,
}: {
  projectId: string
  onImported: () => Promise<void>
}) {
  const [url, setUrl] = useState('')
  const [query, setQuery] = useState('SELECT * FROM ')
  const [name, setName] = useState('')
  const [tables, setTables] = useState<SqlTableInfo[]>([])
  const [preview, setPreview] = useState<SqlPreviewResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleTest() {
    if (!url.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await testSqlConnection(url.trim())
      setMessage(`连接成功：${result.dialect} · ${result.label}`)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleTables() {
    if (!url.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await listSqlTables(url.trim())
      setTables(result.tables)
      setMessage(`发现 ${result.tables.length} 个表/视图（${result.dialect}）`)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handlePreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!url.trim() || !query.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      setPreview(await previewSql(url.trim(), query.trim()))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleImport() {
    if (!url.trim() || !query.trim()) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const dataset = await importSqlDataset(
        projectId,
        url.trim(),
        query.trim(),
        name.trim() || undefined,
      )
      setMessage(`已导入：${dataset.name}（${dataset.row_count} 行）`)
      setPreview(null)
      await onImported()
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h3>数据库导入（SQL）</h3>
      <p className="muted">
        支持 SQLite、PostgreSQL、MySQL；只允许 SELECT/WITH，结果导入为工作区派生
        Parquet，最多 100,000 行。连接串仅用于本次请求，不写入工程。
      </p>
      <div className="stack-form">
        <input
          aria-label="SQL 连接串"
          placeholder="sqlite:///C:/data/app.db 或 postgresql://user:pass@host/db"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
        />
        <div className="inline-form">
          <button className="button" type="button" onClick={() => void handleTest()} disabled={busy}>
            测试连接
          </button>
          <button
            className="button"
            type="button"
            onClick={() => void handleTables()}
            disabled={busy}
          >
            浏览表
          </button>
        </div>
        {tables.length > 0 ? (
          <ul className="dataset-list">
            {tables.map((table) => (
              <li key={`${table.type}-${table.name}`}>
                <button
                  className="list-button"
                  type="button"
                  onClick={() => setQuery(`SELECT * FROM ${table.name}`)}
                  disabled={busy}
                >
                  <span>{table.name}</span>
                  <span className="muted">{table.type}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <form onSubmit={handlePreview} className="stack-form">
          <textarea
            aria-label="SQL 查询"
            rows={5}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="inline-form">
            <input
              aria-label="SQL 数据集名称"
              placeholder="数据集名称（可选）"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <button className="button" type="submit" disabled={busy || !query.trim()}>
              预览查询
            </button>
            <button
              className="button"
              type="button"
              onClick={() => void handleImport()}
              disabled={busy || !query.trim()}
            >
              导入为数据集
            </button>
          </div>
        </form>
      </div>
      {message ? <p className="muted">{message}</p> : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {preview ? (
        <>
          <div className="metrics">
            <span className="metric">方言 <strong>{preview.dialect}</strong></span>
            <span className="metric">返回 <strong>{preview.rows.length}</strong></span>
            <span className="metric">
              截断 <strong>{preview.truncated ? '是' : '否'}</strong>
            </span>
          </div>
          <SqlPreviewTable preview={preview} />
        </>
      ) : null}
    </section>
  )
}
