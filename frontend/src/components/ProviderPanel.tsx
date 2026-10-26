import { useEffect, useState } from 'react'

import { errorMessage } from '../api/projects'
import {
  createProvider,
  deleteProvider,
  listProviderModels,
  listProviderUsage,
  listProviders,
  testProvider,
  updateProvider,
  type Provider,
  type ProviderKind,
  type ProviderTestResult,
  type ProviderUsage,
} from '../api/providers'

type FormState = {
  name: string
  kind: ProviderKind
  base_url: string
  model: string
  api_key: string
  organization: string
  project: string
  anthropic_version: string
  timeout_seconds: string
  max_retries: string
  proxy_url: string
  input_price: string
  output_price: string
  currency: string
  priority: string
  is_default: boolean
  headers: string
  clear_key: boolean
  clear_headers: boolean
}

const EMPTY_FORM: FormState = {
  name: '',
  kind: 'openai',
  base_url: '',
  model: '',
  api_key: '',
  organization: '',
  project: '',
  anthropic_version: '2023-06-01',
  timeout_seconds: '60',
  max_retries: '2',
  proxy_url: '',
  input_price: '0',
  output_price: '0',
  currency: 'USD',
  priority: '100',
  is_default: false,
  headers: '',
  clear_key: false,
  clear_headers: false,
}

function providerToForm(provider: Provider): FormState {
  return {
    name: provider.name,
    kind: provider.kind,
    base_url: provider.base_url,
    model: provider.model,
    api_key: '',
    organization: provider.organization ?? '',
    project: provider.project ?? '',
    anthropic_version: provider.anthropic_version,
    timeout_seconds: String(provider.timeout_seconds),
    max_retries: String(provider.max_retries),
    proxy_url: provider.proxy_url ?? '',
    input_price: String(provider.input_price_per_million),
    output_price: String(provider.output_price_per_million),
    currency: provider.currency,
    priority: String(provider.priority),
    is_default: provider.is_default,
    headers: '',
    clear_key: false,
    clear_headers: false,
  }
}

function parseHeaders(value: string): Record<string, string> | undefined {
  if (!value.trim()) return undefined
  const parsed = JSON.parse(value) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('请求头必须是 JSON 对象')
  }
  return Object.fromEntries(
    Object.entries(parsed as Record<string, unknown>).map(([key, item]) => [key, String(item)]),
  )
}

export function ProviderPanel() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [usage, setUsage] = useState<ProviderUsage[]>([])

  const selected = providers.find((provider) => provider.id === selectedId) ?? null

  useEffect(() => {
    let cancelled = false
    listProviders()
      .then((items) => {
        if (cancelled) return
        setProviders(items)
        if (items.length > 0) {
          setSelectedId(items[0].id)
          setForm(providerToForm(items[0]))
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function refresh(nextId?: string) {
    const items = await listProviders()
    setProviders(items)
    const target = items.find((provider) => provider.id === (nextId ?? selectedId)) ?? items[0]
    if (target) {
      setSelectedId(target.id)
      setForm(providerToForm(target))
    } else {
      setSelectedId(null)
      setForm(EMPTY_FORM)
    }
  }

  function selectProvider(provider: Provider) {
    setSelectedId(provider.id)
    setForm(providerToForm(provider))
    setTestResult(null)
    setModels([])
    setUsage([])
    setError(null)
  }

  function startCreate() {
    setSelectedId(null)
    setForm(EMPTY_FORM)
    setTestResult(null)
    setModels([])
    setUsage([])
    setError(null)
  }

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const headers = parseHeaders(form.headers)
      const payload = {
        name: form.name.trim(),
        kind: form.kind,
        base_url: form.base_url.trim() || null,
        model: form.model.trim(),
        api_key: form.api_key.trim() || undefined,
        headers,
        organization: form.organization.trim() || null,
        project: form.project.trim() || null,
        anthropic_version: form.anthropic_version.trim() || '2023-06-01',
        timeout_seconds: Number(form.timeout_seconds),
        max_retries: Number(form.max_retries),
        proxy_url: form.proxy_url.trim() || null,
        input_price_per_million: Number(form.input_price),
        output_price_per_million: Number(form.output_price),
        currency: form.currency.trim() || 'USD',
        priority: Number(form.priority),
        is_default: form.is_default,
      }
      if (selectedId) {
        await updateProvider(selectedId, {
          ...payload,
          clear_key: form.clear_key,
          clear_headers: form.clear_headers,
        })
        await refresh(selectedId)
      } else {
        const created = await createProvider(payload)
        await refresh(created.id)
      }
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function runTest() {
    if (!selectedId) return
    setBusy(true)
    setError(null)
    try {
      setTestResult(await testProvider(selectedId))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function loadModels() {
    if (!selectedId) return
    setBusy(true)
    setError(null)
    try {
      setModels((await listProviderModels(selectedId)).models)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function loadUsage() {
    if (!selectedId) return
    setBusy(true)
    setError(null)
    try {
      setUsage(await listProviderUsage(selectedId))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!selectedId || !window.confirm(`删除 Provider「${selected?.name ?? ''}」？`)) return
    setBusy(true)
    setError(null)
    try {
      await deleteProvider(selectedId)
      await refresh()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel provider-panel" aria-label="Provider 设置" data-testid="provider-panel">
      <div className="panel-title">
        <div>
          <h3>
            Provider 设置 <span className="badge">P08 预览</span>
          </h3>
          <p className="muted">
            密钥只写入 Windows 凭据管理器；页面仅显示最后四位。价格用于估算费用，不代表账单。
          </p>
        </div>
        <button className="button" onClick={startCreate} disabled={busy}>
          新增 Provider
        </button>
      </div>

      {loading ? <p className="muted">正在加载 Provider…</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="provider-layout">
        <ul className="provider-list">
          {providers.map((provider) => (
            <li key={provider.id}>
              <button
                className={`list-button ${provider.id === selectedId ? 'active' : ''}`}
                onClick={() => selectProvider(provider)}
                disabled={busy}
              >
                <span>
                  {provider.name}
                  {provider.is_default ? ' · 默认' : ''}
                </span>
                <span className="muted">
                  {provider.kind} · {provider.model} · {provider.has_key ? `****${provider.key_last4 ?? ''}` : '无密钥'}
                </span>
              </button>
            </li>
          ))}
          {!loading && providers.length === 0 ? (
            <li className="muted">暂无 Provider，点击“新增 Provider”开始。</li>
          ) : null}
        </ul>

        <div className="provider-form">
          <h4>{selectedId ? `编辑：${selected?.name ?? ''}` : '新增 Provider'}</h4>
          <div className="stack-form">
            <label>
              名称
              <input value={form.name} onChange={(event) => updateField('name', event.target.value)} />
            </label>
            <label>
              类型
              <select
                value={form.kind}
                onChange={(event) => updateField('kind', event.target.value as ProviderKind)}
              >
                <option value="openai">OpenAI 兼容</option>
                <option value="anthropic">Anthropic 兼容</option>
              </select>
            </label>
            <label>
              Base URL
              <input
                placeholder="留空使用官方默认地址"
                value={form.base_url}
                onChange={(event) => updateField('base_url', event.target.value)}
              />
            </label>
            <label>
              模型
              <input value={form.model} onChange={(event) => updateField('model', event.target.value)} />
            </label>
            <label>
              API Key（留空保持不变）
              <input
                type="password"
                autoComplete="off"
                value={form.api_key}
                onChange={(event) => updateField('api_key', event.target.value)}
              />
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(event) => updateField('is_default', event.target.checked)}
              />
              设为默认 Provider
            </label>

            <details className="advanced-options">
              <summary>高级设置</summary>
              <div className="stack-form">
                <label>
                  组织（OpenAI）
                  <input
                    value={form.organization}
                    onChange={(event) => updateField('organization', event.target.value)}
                  />
                </label>
                <label>
                  项目（OpenAI）
                  <input
                    value={form.project}
                    onChange={(event) => updateField('project', event.target.value)}
                  />
                </label>
                <label>
                  Anthropic 版本头
                  <input
                    value={form.anthropic_version}
                    onChange={(event) => updateField('anthropic_version', event.target.value)}
                  />
                </label>
                <label>
                  超时（秒）
                  <input
                    value={form.timeout_seconds}
                    onChange={(event) => updateField('timeout_seconds', event.target.value)}
                  />
                </label>
                <label>
                  最大重试
                  <input
                    value={form.max_retries}
                    onChange={(event) => updateField('max_retries', event.target.value)}
                  />
                </label>
                <label>
                  代理 URL
                  <input
                    value={form.proxy_url}
                    onChange={(event) => updateField('proxy_url', event.target.value)}
                  />
                </label>
                <label>
                  输入价格 / 百万 Token
                  <input
                    value={form.input_price}
                    onChange={(event) => updateField('input_price', event.target.value)}
                  />
                </label>
                <label>
                  输出价格 / 百万 Token
                  <input
                    value={form.output_price}
                    onChange={(event) => updateField('output_price', event.target.value)}
                  />
                </label>
                <label>
                  货币
                  <input
                    value={form.currency}
                    onChange={(event) => updateField('currency', event.target.value)}
                  />
                </label>
                <label>
                  优先级（越小越靠前）
                  <input
                    value={form.priority}
                    onChange={(event) => updateField('priority', event.target.value)}
                  />
                </label>
                <label>
                  自定义请求头（JSON，值存入凭据管理器）
                  <textarea
                    rows={3}
                    value={form.headers}
                    onChange={(event) => updateField('headers', event.target.value)}
                  />
                </label>
                {selectedId ? (
                  <>
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={form.clear_key}
                        onChange={(event) => updateField('clear_key', event.target.checked)}
                      />
                      清除已保存密钥
                    </label>
                    <label className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={form.clear_headers}
                        onChange={(event) => updateField('clear_headers', event.target.checked)}
                      />
                      清除已保存请求头（{selected?.header_names.join('、') || '无'}）
                    </label>
                  </>
                ) : null}
              </div>
            </details>
          </div>

          <div className="inline-form">
            <button className="button" onClick={save} disabled={busy}>
              保存
            </button>
            <button className="button" onClick={runTest} disabled={busy || !selectedId}>
              测试连接
            </button>
            <button className="button" onClick={loadModels} disabled={busy || !selectedId}>
              模型列表
            </button>
            <button className="button" onClick={loadUsage} disabled={busy || !selectedId}>
              最近用量
            </button>
            <button className="button" onClick={remove} disabled={busy || !selectedId}>
              删除
            </button>
          </div>

          {testResult ? (
            <p className="muted" data-testid="provider-test-result">
              连接正常 · {testResult.latency_ms} ms ·{' '}
              {testResult.models_supported ? '支持模型列表' : '不提供模型列表'}
              {testResult.message ? ` · ${testResult.message}` : ''}
            </p>
          ) : null}
          {models.length > 0 ? (
            <div className="chips">
              {models.slice(0, 12).map((model) => (
                <span className="chip" key={model}>
                  {model}
                </span>
              ))}
            </div>
          ) : null}
          {usage.length > 0 ? (
            <div className="table-wrap">
              <table className="preview-table">
                <thead>
                  <tr>
                    <th>模型</th>
                    <th>输入</th>
                    <th>输出</th>
                    <th>费用</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.map((item) => (
                    <tr key={item.id}>
                      <td>{item.model}</td>
                      <td>{item.input_tokens}</td>
                      <td>{item.output_tokens}</td>
                      <td>
                        {item.estimated_cost.toFixed(6)} {item.currency}
                      </td>
                      <td>{new Date(item.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  )
}
