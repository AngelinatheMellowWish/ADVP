import { request } from './projects'

export type SettingSource = 'env' | 'settings' | 'default'

export type SettingValue<T = unknown> = {
  value: T
  source: SettingSource
}

export type Eu2Settings = Record<string, SettingValue>

export async function getSettings(): Promise<Eu2Settings> {
  return request<Eu2Settings>('/api/settings')
}

export async function updateSettings(
  input: Record<string, unknown>,
): Promise<Eu2Settings> {
  return request<Eu2Settings>('/api/settings', {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}
