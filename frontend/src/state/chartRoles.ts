export const OPTIONAL_ROLE_GROUPS: Record<string, string> = {
  series: 'categorical',
  facet: 'categorical',
  x: 'categorical',
  y: 'numeric',
  y2: 'numeric',
  error_y: 'numeric',
  size: 'numeric',
  value: 'numeric',
  label: 'categorical',
  weight: 'numeric',
  level1: 'categorical',
  level2: 'categorical',
  level3: 'categorical',
  region: 'categorical',
  track: 'categorical',
  time: 'temporal',
  latitude: 'geo',
  longitude: 'geo',
  source: 'categorical',
  target: 'categorical',
}

export const SEMANTIC_GROUPS: Record<string, string[]> = {
  integer: ['numeric'],
  number: ['numeric'],
  duration: ['numeric'],
  datetime: ['temporal'],
  date: ['temporal'],
  time: ['temporal'],
  categorical: ['categorical'],
  boolean: ['categorical', 'boolean'],
  string: ['categorical', 'text'],
  email: ['categorical', 'text'],
  phone: ['categorical', 'text'],
  id_card_number: ['categorical', 'text'],
  address: ['categorical', 'text'],
  url: ['categorical', 'text'],
  geo_coordinate: ['numeric', 'geo'],
  array: ['array'],
  object: [],
  binary: [],
  null: [],
  unknown: [],
}

export function matchesGroup(semanticType: string, group: string): boolean {
  if (group === 'any') return true
  return (SEMANTIC_GROUPS[semanticType] ?? []).includes(group)
}

export function roleGroup(
  role: string,
  requiredTypes: Record<string, string>,
): string {
  return requiredTypes[role] ?? OPTIONAL_ROLE_GROUPS[role] ?? 'any'
}
