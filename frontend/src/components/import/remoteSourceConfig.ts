export function parseHeaderLines(raw: string): Record<string, string> {
  const headers: Record<string, string> = {}
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const separator = trimmed.indexOf(':')
    if (separator <= 0) continue
    const name = trimmed.slice(0, separator).trim()
    const value = trimmed.slice(separator + 1).trim()
    if (name) headers[name] = value
  }
  return headers
}

export function combineS3Key(prefix: string, key: string): string {
  const cleanKey = key.trim().replace(/^\/+/, '')
  const cleanPrefix = prefix.trim().replace(/\/+$/, '')
  if (!cleanPrefix) return cleanKey
  if (!cleanKey) return cleanPrefix
  return `${cleanPrefix}/${cleanKey}`
}

export function isValidHttpUrl(value: string): boolean {
  return /^https?:\/\/\S+$/i.test(value.trim())
}
