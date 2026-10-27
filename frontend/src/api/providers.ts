import { request } from './projects'

export type ProviderKind = 'openai' | 'anthropic'

export type Provider = {
  id: string
  name: string
  kind: ProviderKind
  base_url: string
  model: string
  organization: string | null
  project: string | null
  anthropic_version: string
  timeout_seconds: number
  max_retries: number
  proxy_url: string | null
  input_price_per_million: number
  output_price_per_million: number
  currency: string
  priority: number
  is_default: boolean
  key_last4: string | null
  has_key: boolean
  header_names: string[]
  created_at: string
  updated_at: string
}

export type ProviderCreateInput = {
  name: string
  kind: ProviderKind
  base_url?: string | null
  model: string
  api_key?: string | null
  headers?: Record<string, string> | null
  organization?: string | null
  project?: string | null
  anthropic_version?: string
  timeout_seconds?: number
  max_retries?: number
  proxy_url?: string | null
  input_price_per_million?: number
  output_price_per_million?: number
  currency?: string
  priority?: number
  is_default?: boolean
}

export type ProviderUpdateInput = Partial<ProviderCreateInput> & {
  clear_key?: boolean
  clear_headers?: boolean
}

export type ProviderTestResult = {
  ok: boolean
  latency_ms: number
  models_supported: boolean
  message: string | null
}

export type ProviderModelsResult = {
  models: string[]
  latency_ms: number
}

export type ProviderUsage = {
  id: string
  provider_id: string | null
  provider_name: string
  kind: string
  model: string
  operation: string
  input_tokens: number
  output_tokens: number
  cached_tokens: number
  latency_ms: number
  estimated_cost: number
  currency: string
  attempts: number
  created_at: string
}

export async function listProviders(): Promise<Provider[]> {
  return request<Provider[]>('/api/providers')
}

export async function createProvider(input: ProviderCreateInput): Promise<Provider> {
  return request<Provider>('/api/providers', {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function updateProvider(
  providerId: string,
  input: ProviderUpdateInput,
): Promise<Provider> {
  return request<Provider>(`/api/providers/${providerId}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function deleteProvider(providerId: string): Promise<void> {
  return request<void>(`/api/providers/${providerId}`, { method: 'DELETE' })
}

export async function testProvider(providerId: string): Promise<ProviderTestResult> {
  return request<ProviderTestResult>(`/api/providers/${providerId}/test`, {
    method: 'POST',
  })
}

export async function listProviderModels(providerId: string): Promise<ProviderModelsResult> {
  return request<ProviderModelsResult>(`/api/providers/${providerId}/models`)
}

export async function listProviderUsage(
  providerId: string,
  limit = 20,
): Promise<ProviderUsage[]> {
  return request<ProviderUsage[]>(`/api/providers/${providerId}/usage?limit=${limit}`)
}
