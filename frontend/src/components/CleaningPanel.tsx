import { useState } from 'react'

import {
  cleanDataset,
  rollbackCleaning,
  undoCleaning,
  type CleanOperation,
  type CleanResponse,
  type CleanStep,
} from '../api/cleaning'
import { errorMessage, type ColumnDefinition } from '../api/projects'

const OPERATIONS: { value: CleanOperation; label: string }[] = [
  { value: 'drop_missing', label: '删除缺失行' },
  { value: 'fill_missing', label: '填充缺失值' },
  { value: 'clip_outliers', label: '截断异常值' },
  { value: 'deduplicate', label: '去重' },
  { value: 'cast_type', label: '类型转换' },
  { value: 'rename_columns', label: '重命名列' },
  { value: 'drop_columns', label: '删除列（高风险）' },
]

const FILL_STRATEGIES = ['mean', 'median', 'mode', 'forward', 'constant']
const CLIP_METHODS = ['iqr', 'zscore', 'quantile', 'winsorize']
const CAST_TARGETS = ['int', 'float', 'string', 'boolean', 'date', 'datetime']

function choices(operation: CleanOperation): string[] {
  if (operation === 'fill_missing') return FILL_STRATEGIES
  if (operation === 'clip_outliers') return CLIP_METHODS
  if (operation === 'cast_type') return CAST_TARGETS
  return []
}

function splitColumns(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function CleaningPanel({
  datasetId,
  columns,
}: {
  datasetId: string
  columns: ColumnDefinition[]
}) {
  const [operation, setOperation] = useState<CleanOperation>('drop_missing')
  const [columnsText, setColumnsText] = useState('')
  const [column, setColumn] = useState(columns[0]?.name ?? '')
  const [option, setOption] = useState('mean')
  const [value, setValue] = useState('')
  const [mappingText, setMappingText] = useState('')
  const [confirmHighRisk, setConfirmHighRisk] = useState(false)
  const [steps, setSteps] = useState<CleanStep[]>([])
  const [result, setResult] = useState<CleanResponse | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function buildStep(): CleanStep | null {
    const selectedColumns = splitColumns(columnsText)
    if (operation === 'drop_missing' || operation === 'drop_columns') {
      if (selectedColumns.length === 0) return null
      return { operation, columns: selectedColumns }
    }
    if (operation === 'fill_missing') {
      if (!column) return null
      return {
        operation,
        column,
        strategy: option,
        value: option === 'constant' ? value : undefined,
      }
    }
    if (operation === 'clip_outliers') {
      if (!column) return null
      return { operation, column, method: option, factor: 1.5 }
    }
    if (operation === 'cast_type') {
      if (!column) return null
      return { operation, column, target: option }
    }
    if (operation === 'deduplicate') {
      return { operation, subset: selectedColumns.length ? selectedColumns : undefined }
    }
    try {
      const mapping = JSON.parse(mappingText) as unknown
      if (!mapping || typeof mapping !== 'object' || Array.isArray(mapping)) return null
      return {
        operation,
        mapping: Object.fromEntries(
          Object.entries(mapping as Record<string, unknown>).map(([key, item]) => [
            key,
            String(item),
          ]),
        ),
      }
    } catch {
      return null
    }
  }

  function addStep() {
    const step = buildStep()
    if (!step) {
      setError('请填写该操作需要的字段或参数。')
      return
    }
    setSteps((current) => [...current, step])
    setError(null)
  }

  function removeStep(index: number) {
    setSteps((current) => current.filter((_, itemIndex) => itemIndex !== index))
  }

  async function run(dryRun: boolean) {
    if (steps.length === 0) {
      setError('请先添加至少一个清洗步骤。')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const response = await cleanDataset(datasetId, steps, { dryRun, confirmHighRisk })
      setResult(response)
      setRunId(response.cleaning_run_id)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function undo() {
    if (!runId) return
    setBusy(true)
    setError(null)
    try {
      const response = await undoCleaning(runId)
      setRunId(response.cleaning_run_id)
      setResult(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function rollback() {
    if (!runId) return
    setBusy(true)
    setError(null)
    try {
      await rollbackCleaning(runId)
      setRunId(null)
      setResult(null)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const optionChoices = choices(operation)

  return (
    <section className="cleaning-panel" aria-label="数据清洗" data-testid="cleaning-panel">
      <div className="panel-title">
        <div>
          <h4>
            数据清洗 <span className="badge">派生数据</span>
          </h4>
          <p className="muted">
            最多读取 100,000 行生成派生 Parquet；原始文件不被修改。删除列需要显式确认。
          </p>
        </div>
      </div>

      <div className="cleaning-form">
        <label>
          操作
          <select
            value={operation}
            onChange={(event) => {
              const next = event.target.value as CleanOperation
              setOperation(next)
              const nextChoices = choices(next)
              setOption(nextChoices[0] ?? '')
            }}
          >
            {OPERATIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        {['drop_missing', 'drop_columns', 'deduplicate'].includes(operation) ? (
          <label>
            列（逗号分隔，去重可留空）
            <input
              value={columnsText}
              onChange={(event) => setColumnsText(event.target.value)}
            />
          </label>
        ) : null}

        {['fill_missing', 'clip_outliers', 'cast_type'].includes(operation) ? (
          <label>
            列
            <select value={column} onChange={(event) => setColumn(event.target.value)}>
              {columns.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {optionChoices.length > 0 ? (
          <label>
            策略 / 目标
            <select value={option} onChange={(event) => setOption(event.target.value)}>
              {optionChoices.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {operation === 'fill_missing' && option === 'constant' ? (
          <label>
            常量值
            <input value={value} onChange={(event) => setValue(event.target.value)} />
          </label>
        ) : null}

        {operation === 'rename_columns' ? (
          <label>
            重命名映射（JSON）
            <input
              placeholder='{"old": "new"}'
              value={mappingText}
              onChange={(event) => setMappingText(event.target.value)}
            />
          </label>
        ) : null}

        {operation === 'drop_columns' ? (
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={confirmHighRisk}
              onChange={(event) => setConfirmHighRisk(event.target.checked)}
            />
            我确认删除这些列
          </label>
        ) : null}

        <button className="button" onClick={addStep} disabled={busy}>
          添加步骤
        </button>
      </div>

      {steps.length > 0 ? (
        <ol className="cleaning-steps">
          {steps.map((step, index) => (
            <li key={`${step.operation}-${index}`}>
              <strong>{step.operation}</strong>
              <span className="muted">
                {step.column ?? ''}
                {step.columns ? ` ${step.columns.join('、')}` : ''}
                {step.target ? ` → ${step.target}` : ''}
                {step.strategy ? ` (${step.strategy})` : ''}
                {step.method ? ` (${step.method})` : ''}
              </span>
              <button className="button" onClick={() => removeStep(index)} disabled={busy}>
                移除
              </button>
            </li>
          ))}
        </ol>
      ) : null}

      <div className="inline-form">
        <button className="button" onClick={() => run(true)} disabled={busy || steps.length === 0}>
          预览清洗
        </button>
        <button className="button" onClick={() => run(false)} disabled={busy || steps.length === 0}>
          应用清洗
        </button>
        {runId ? (
          <>
            <button className="button" onClick={undo} disabled={busy}>
              撤销上一步
            </button>
            <button className="button" onClick={rollback} disabled={busy}>
              回滚原数据
            </button>
          </>
        ) : null}
      </div>

      {error ? <p className="error">{error}</p> : null}
      {result ? (
        <div className="cleaning-result" data-testid="cleaning-result">
          <p className="muted">
            {result.dry_run ? '预览' : '已应用'} · {result.before_rows} → {result.after_rows} 行
            {result.truncated ? ' · 基于采样' : ''}
            {result.derived_dataset_id ? ` · 派生数据集 ${result.derived_dataset_id}` : ''}
          </p>
          <ul className="issues">
            {result.log.map((entry) => (
              <li className="issue info" key={`${entry.step}-${entry.operation}`}>
                <span className="issue-severity">步骤 {entry.step + 1}</span>
                <strong>{entry.operation}</strong>
                <span>
                  影响 {entry.affected_rows} 行
                  {entry.column ? ` · ${entry.column}` : ''}
                  {entry.columns ? ` · ${entry.columns.join('、')}` : ''}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
