export type AdvancedFileOptionsValue = {
  encoding: string
  delimiter: string
  hasHeader: boolean
  sampleRows: number
  sheetOrVariable: string
  missingMarkers: string
  typeOverrides: string
}

export const DEFAULT_ADVANCED_FILE_OPTIONS: AdvancedFileOptionsValue = {
  encoding: '',
  delimiter: '',
  hasHeader: true,
  sampleRows: 100_000,
  sheetOrVariable: '',
  missingMarkers: '',
  typeOverrides: '',
}

export const MAX_SAMPLE_ROWS = 100_000

const TYPE_OVERRIDE_PATTERN = /^[^=,\s]+=\S+$/

export function parseMissingMarkers(raw: string): string[] {
  return raw
    .split(',')
    .map((marker) => marker.trim())
    .filter(Boolean)
}

export function parseTypeOverrides(raw: string): Record<string, string> {
  const overrides: Record<string, string> = {}
  for (const pair of raw.split(',')) {
    const trimmed = pair.trim()
    if (!trimmed) continue
    const separator = trimmed.indexOf('=')
    if (separator < 0) continue
    const column = trimmed.slice(0, separator).trim()
    const type = trimmed.slice(separator + 1).trim()
    if (column && type) overrides[column] = type
  }
  return overrides
}

export function hasInvalidTypeOverrides(raw: string): boolean {
  return raw
    .split(',')
    .map((pair) => pair.trim())
    .filter(Boolean)
    .some((pair) => !TYPE_OVERRIDE_PATTERN.test(pair))
}

export function isAdvancedFileOptionsValid(values: AdvancedFileOptionsValue): boolean {
  const delimiterValid = values.delimiter.length === 0 || values.delimiter.length === 1
  const sampleRowsValid =
    Number.isInteger(values.sampleRows) &&
    values.sampleRows >= 1 &&
    values.sampleRows <= MAX_SAMPLE_ROWS
  return delimiterValid && sampleRowsValid && !hasInvalidTypeOverrides(values.typeOverrides)
}
