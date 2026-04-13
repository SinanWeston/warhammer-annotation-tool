export const BATTLEFIELD_ROLES = [
  { key: 'hq', label: 'HQ', description: 'Command units and leaders' },
  { key: 'troops', label: 'Troops', description: 'Core battleline units' },
  { key: 'elites', label: 'Elites', description: 'Specialized infantry and support' },
  { key: 'fast_attack', label: 'Fast Attack', description: 'Mobile strike units' },
  { key: 'heavy_support', label: 'Heavy Support', description: 'Heavy weapons and vehicles' },
  { key: 'dedicated_transport', label: 'Dedicated Transport', description: 'Unit transports' },
  { key: 'lord_of_war', label: 'Lord of War', description: 'Super-heavy units and titans' },
  { key: 'fortification', label: 'Fortification', description: 'Defensive structures' },
] as const

export type BattlefieldRole = typeof BATTLEFIELD_ROLES[number]['key']

export const ROLE_MAP = new Map<string, typeof BATTLEFIELD_ROLES[number]>(
  BATTLEFIELD_ROLES.map(r => [r.key, r])
)

export function getRoleLabel(key: string): string {
  return ROLE_MAP.get(key)?.label ?? key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
