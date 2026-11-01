import { useEffect, useState, type FormEvent } from 'react'

import {
  createProject,
  errorMessage,
  formatBytes,
  getDataset,
  getProject,
  importDataset,
  inspectDataset,
  listProjects,
  reprofileDataset,
  type DatasetDetail,
  type ImportOptionsInput,
  type InspectResponse,
  type ProfileIssue,
  type ProjectDetail,
  type ProjectSummary,
} from '../api/projects'
import { AnalysisPanel } from './AnalysisPanel'
import { ChartCandidatesPanel } from './ChartCandidatesPanel'
import { CleaningPanel } from './CleaningPanel'
import { ChartSelectionPanel } from './ChartSelectionPanel'
import { CostPanel } from './CostPanel'
import { LiveStreamPanel } from './LiveStreamPanel'
import { MoreSourcesPanel } from './MoreSourcesPanel'
import { PipelinePanel } from './PipelinePanel'
import { ScenePanel } from './ScenePanel'
import { SqlImportPanel } from './SqlImportPanel'

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function optionValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '自动'
  return String(value)
}

function renderStat(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(4)
}

function previewColumns(
  columns: { name: string }[],
  rows: Record<string, unknown>[],
): string[] {
  if (columns.length > 0) return columns.map((column) => column.name)
  return rows.length > 0 ? Object.keys(rows[0]) : []
}

function ArraySummary({
  shape,
  dims,
  dtype,
  units,
  stats,
}: {
  shape: number[]
  dims: string[]
  dtype: string
  units: string | null
  stats: Record<string, number | null>
}) {
  return (
    <div className="metrics">
      <span className="metric">形状 <strong>{shape.join(' × ') || '标量'}</strong></span>
      <span className="metric">维度 <strong>{dims.join(', ') || '—'}</strong></span>
      <span className="metric">类型 <strong>{dtype}</strong></span>
      <span className="metric">单位 <strong>{units ?? '—'}</strong></span>
      <span className="metric">最小 <strong>{renderStat(stats.min)}</strong></span>
      <span className="metric">最大 <strong>{renderStat(stats.max)}</strong></span>
      <span className="metric">均值 <strong>{renderStat(stats.mean)}</strong></span>
    </div>
  )
}

function IssueList({ issues }: { issues: ProfileIssue[] }) {
  if (issues.length === 0) {
    return <p className="muted">未发现质量问题。</p>
  }
  return (
    <ul className="issues">
      {issues.map((issue, index) => (
        <li className={`issue ${issue.severity}`} key={`${issue.code}-${issue.column ?? ''}-${index}`}>
          <span className="issue-severity">{issue.severity}</span>
          <span>{issue.message}</span>
          {issue.suggestion ? <span className="muted">建议：{issue.suggestion}</span> : null}
        </li>
      ))}
    </ul>
  )
}

function DataTable({
  columns,
  rows,
}: {
  columns: string[]
  rows: Record<string, unknown>[]
}) {
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
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length}>没有数据行。</td>
            </tr>
          ) : (
            rows.map((row, index) => (
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

function DatasetPanel({
  dataset,
  onReprofile,
  busy,
}: {
  dataset: DatasetDetail
  onReprofile: () => void
  busy: boolean
}) {
  const issues = [...dataset.profile.issues, ...(dataset.profile.import_issues ?? [])]
  const columns = previewColumns(dataset.schema_definition.columns, dataset.preview)
  const array = dataset.profile.array
  return (
    <section className="panel">
      <div className="panel-title">
        <div>
          <h3>{dataset.name}</h3>
          <p className="muted">
            v{dataset.version} · {dataset.format} · {dataset.row_count} 行 ·{' '}
            {dataset.column_count} 列 · {formatBytes(dataset.source_size)}
            {dataset.sampled ? ' · 基于采样' : ''}
          </p>
        </div>
        <button className="button" onClick={onReprofile} disabled={busy}>
          重新画像
        </button>
      </div>
      <div className="metrics">
        <span className="metric">质量评分 <strong>{dataset.quality_score}</strong></span>
        <span className="metric">重复行 <strong>{dataset.profile.duplicate_rows}</strong></span>
        <span className="metric">缺失单元 <strong>{dataset.profile.summary.missing_cells}</strong></span>
        <span className="metric">
          敏感列 <strong>{dataset.profile.summary.sensitive_columns.length}</strong>
        </span>
      </div>
      {array ? (
        <ArraySummary
          shape={array.shape}
          dims={array.dims}
          dtype={array.dtype}
          units={array.units}
          stats={array.stats}
        />
      ) : null}
      {dataset.profile.summary.sensitive_columns.length > 0 ? (
        <p className="muted">
          敏感字段：{dataset.profile.summary.sensitive_columns.join('、')}（默认脱敏后再发送给模型）
        </p>
      ) : null}
      <DataTable columns={columns} rows={dataset.preview} />
      <h4>质量问题</h4>
      <IssueList issues={issues} />
      <AnalysisPanel datasetId={dataset.id} />
      <CleaningPanel datasetId={dataset.id} columns={dataset.schema_definition.columns} />
      <ChartCandidatesPanel datasetId={dataset.id} datasetKind={dataset.kind} />
      <ChartSelectionPanel datasetId={dataset.id} />
      <ScenePanel datasetId={dataset.id} datasetKind={dataset.kind} />
      <PipelinePanel datasetId={dataset.id} />
      <p className="muted source-path">来源：{dataset.source_path}</p>
    </section>
  )
}

export function DataWorkbench() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [dataset, setDataset] = useState<DatasetDetail | null>(null)
  const [inspect, setInspect] = useState<InspectResponse | null>(null)
  const [projectName, setProjectName] = useState('')
  const [datasetPath, setDatasetPath] = useState('')
  const [datasetName, setDatasetName] = useState('')
  const [rawShape, setRawShape] = useState('')
  const [rawDtype, setRawDtype] = useState('')
  const [rawByteOrder, setRawByteOrder] = useState('native')
  const [rawOffset, setRawOffset] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    listProjects()
      .then((items) => {
        if (!cancelled) setProjects(items)
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(errorMessage(caught))
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!projectName.trim()) return
    setBusy(true)
    setError(null)
    try {
      const created = await createProject(projectName.trim())
      setProjects(await listProjects())
      setProject(created)
      setDataset(null)
      setInspect(null)
      setProjectName('')
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function openProject(projectId: string) {
    setBusy(true)
    setError(null)
    try {
      const opened = await getProject(projectId)
      setProject(opened)
      setDataset(null)
      setInspect(null)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  function buildImportOptions(): ImportOptionsInput {
    const options: ImportOptionsInput = {}
    const shapeText = rawShape.trim()
    if (shapeText) {
      const shape = shapeText
        .split(/[,\s]+/)
        .map((part) => Number(part))
        .filter((value) => Number.isFinite(value) && value > 0)
      if (shape.length > 0) options.shape = shape
    }
    if (rawDtype.trim()) options.dtype = rawDtype.trim()
    if (rawByteOrder !== 'native') options.byte_order = rawByteOrder
    if (rawOffset.trim()) {
      const offset = Number(rawOffset)
      if (Number.isFinite(offset) && offset >= 0) options.raw_offset = offset
    }
    return options
  }

  async function handleInspect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!project || !datasetPath.trim()) return
    const path = datasetPath.trim()
    setError(null)
    setInspect(null)
    setDataset(null)
    if (/\.(pdf|docx|txt|md|rtf|html?)$/i.test(path)) {
      setError(
        '文档请在下方“更多数据源 → 文档 / 文本统计”中检查并导入；支持表格与正文数字统计，扫描件不做 OCR。',
      )
      return
    }
    setBusy(true)
    try {
      setInspect(await inspectDataset(project.id, path, buildImportOptions()))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleInspectVariable(variable: string) {
    if (!project || !inspect) return
    setBusy(true)
    setError(null)
    try {
      const selected = await inspectDataset(project.id, inspect.path, {
        ...buildImportOptions(),
        variable,
      })
      setInspect(selected)
      if (!datasetName.trim()) setDatasetName(variable)
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleImport() {
    if (!project || !inspect) return
    const variable =
      typeof inspect.options.variable === 'string' ? inspect.options.variable : undefined
    if (inspect.kind === 'array' && !variable) return
    setBusy(true)
    setError(null)
    try {
      const imported = await importDataset(
        project.id,
        inspect.path,
        datasetName.trim(),
        { ...buildImportOptions(), ...(variable ? { variable } : {}) },
      )
      setDataset(imported)
      setInspect(null)
      setDatasetName('')
      setProject(await getProject(project.id))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function openDataset(datasetId: string) {
    setBusy(true)
    setError(null)
    try {
      setDataset(await getDataset(datasetId))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleReprofile() {
    if (!dataset) return
    setBusy(true)
    setError(null)
    try {
      setDataset(await reprofileDataset(dataset.id))
    } catch (caught) {
      setError(errorMessage(caught))
    } finally {
      setBusy(false)
    }
  }

  async function handleSqlImported() {
    if (!project) return
    try {
      setProject(await getProject(project.id))
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  const selectedVariable =
    inspect && typeof inspect.options.variable === 'string'
      ? inspect.options.variable
      : null
  const canImport = inspect ? inspect.kind !== 'array' || Boolean(selectedVariable) : false

  return (
    <section className="workbench">
      <div className="section-heading">
        <div>
          <p className="eyebrow">M2 · Data ingestion</p>
          <h2>数据工作台</h2>
          <p className="muted">新建工程、检查本地文件、导入并查看画像与质量问题。</p>
        </div>
      </div>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="workbench-grid">
        <section className="panel">
          <h3>工程</h3>
          <form onSubmit={handleCreateProject} className="inline-form">
            <input
              aria-label="工程名称"
              placeholder="新工程名称"
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
            />
            <button className="button" type="submit" disabled={busy || !projectName.trim()}>
              新建
            </button>
          </form>
          {!loaded ? <p className="muted">正在加载工程…</p> : null}
          {loaded && projects.length === 0 ? <p className="muted">暂无工程。</p> : null}
          <ul className="project-list">
            {projects.map((item) => (
              <li key={item.id}>
                <button
                  className={`list-button ${project?.id === item.id ? 'active' : ''}`}
                  onClick={() => void openProject(item.id)}
                  disabled={busy}
                >
                  <span>{item.name}</span>
                  <span className="muted">{item.dataset_count} 个数据集</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h3>导入数据</h3>
          {!project ? (
            <p className="muted">先选择或新建一个工程。</p>
          ) : (
            <>
              <p className="muted">当前工程：{project.name}</p>
              <form onSubmit={handleInspect} className="stack-form">
                <input
                  aria-label="文件路径"
                  placeholder="本地文件绝对路径，例如 C:/data/example.csv"
                  value={datasetPath}
                  onChange={(event) => setDatasetPath(event.target.value)}
                />
                <input
                  aria-label="数据集名称"
                  placeholder="数据集名称（可选）"
                  value={datasetName}
                  onChange={(event) => setDatasetName(event.target.value)}
                />
                <details className="advanced-options">
                  <summary>RAW / 高级选项</summary>
                  <div className="stack-form">
                    <input
                      aria-label="RAW shape"
                      placeholder="shape，例如 256,256,128"
                      value={rawShape}
                      onChange={(event) => setRawShape(event.target.value)}
                    />
                    <input
                      aria-label="RAW dtype"
                      placeholder="dtype，例如 int16 / float32"
                      value={rawDtype}
                      onChange={(event) => setRawDtype(event.target.value)}
                    />
                    <select
                      aria-label="字节序"
                      value={rawByteOrder}
                      onChange={(event) => setRawByteOrder(event.target.value)}
                    >
                      <option value="native">字节序：原生</option>
                      <option value="little">小端 little</option>
                      <option value="big">大端 big</option>
                    </select>
                    <input
                      aria-label="RAW 字节偏移"
                      type="number"
                      min="0"
                      placeholder="字节偏移（可选）"
                      value={rawOffset}
                      onChange={(event) => setRawOffset(event.target.value)}
                    />
                  </div>
                </details>
                <button
                  className="button"
                  type="submit"
                  disabled={busy || !datasetPath.trim()}
                >
                  检查文件
                </button>
              </form>
              <p className="muted">
                支持 CSV、TSV、JSON/JSONL、Parquet、Excel、HDF5、NetCDF、FITS、DICOM
                序列、NIfTI、RAW；RAW 需填 shape/dtype，单文件上限按后端配置。
              </p>
            </>
          )}
        </section>
      </div>

      {project ? (
        <>
          <SqlImportPanel projectId={project.id} onImported={handleSqlImported} />
          <MoreSourcesPanel projectId={project.id} onImported={handleSqlImported} />
          <LiveStreamPanel projectId={project.id} />
        </>
      ) : null}

      {inspect ? (
        <section className="panel">
          <div className="panel-title">
            <div>
              <h3>导入预览</h3>
              <p className="muted">
                {inspect.format} ·{' '}
                {inspect.kind === 'array' ? '数组' : `${inspect.row_count} 行`} ·{' '}
                {formatBytes(inspect.size_bytes)}
                {inspect.sampled ? ' · 基于采样' : ''}
              </p>
            </div>
            <button
              className="button"
              onClick={() => void handleImport()}
              disabled={busy || !canImport}
            >
              确认导入
            </button>
          </div>
          <div className="metrics">
            <span className="metric">质量评分 <strong>{inspect.profile.quality_score}</strong></span>
            {inspect.kind !== 'array' ? (
              <>
                <span className="metric">
                  编码 <strong>{optionValue(inspect.options.encoding)}</strong>
                </span>
                <span className="metric">
                  分隔符 <strong>{optionValue(inspect.options.delimiter)}</strong>
                </span>
                <span className="metric">
                  表头 <strong>{optionValue(inspect.options.has_header)}</strong>
                </span>
              </>
            ) : null}
          </div>
          {inspect.kind === 'array' && inspect.variables.length > 0 ? (
            <>
              <h4>变量</h4>
              <ul className="dataset-list">
                {inspect.variables.map((variable) => (
                  <li key={variable.path}>
                    <button
                      className={`list-button ${
                        selectedVariable === variable.path ? 'active' : ''
                      }`}
                      onClick={() => void handleInspectVariable(variable.path)}
                      disabled={busy}
                    >
                      <span>{variable.name}</span>
                      <span className="muted">
                        {variable.shape.join(' × ')} · {variable.dtype}
                        {variable.units ? ` · ${variable.units}` : ''}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {inspect.kind === 'array' && inspect.profile.array ? (
            <ArraySummary
              shape={inspect.profile.array.shape}
              dims={inspect.profile.array.dims}
              dtype={inspect.profile.array.dtype}
              units={inspect.profile.array.units}
              stats={inspect.profile.array.stats}
            />
          ) : null}
          {Object.keys(inspect.detected).length > 0 ? (
            <p className="muted">
              自动识别：
              {Object.entries(inspect.detected)
                .map(([key, value]) => `${key}=${String(value)}`)
                .join('，')}
            </p>
          ) : null}
          {inspect.kind === 'array' && !selectedVariable ? (
            <p className="muted">选择一个变量以生成画像和预览。</p>
          ) : (
            <DataTable
              columns={previewColumns(inspect.schema_definition.columns, inspect.preview)}
              rows={inspect.preview}
            />
          )}
          <h4>质量问题</h4>
          <IssueList issues={inspect.issues} />
        </section>
      ) : null}

      {project ? <CostPanel projectId={project.id} /> : null}

      {project && project.datasets.length > 0 ? (
        <section className="panel">
          <h3>数据集</h3>
          <ul className="dataset-list">
            {project.datasets.map((item) => (
              <li key={item.id}>
                <button
                  className={`list-button ${dataset?.id === item.id ? 'active' : ''}`}
                  onClick={() => void openDataset(item.id)}
                  disabled={busy}
                >
                  <span>
                    {item.name} · v{item.version}
                  </span>
                  <span className="muted">
                    {item.row_count} 行 · 质量 {item.quality_score}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {dataset ? (
        <DatasetPanel dataset={dataset} onReprofile={() => void handleReprofile()} busy={busy} />
      ) : null}
    </section>
  )
}
