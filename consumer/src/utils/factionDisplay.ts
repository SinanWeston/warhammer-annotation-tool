import { FACTION_MAP } from './factions'

/** Returns the correct display name for a faction key.
 *  Uses the canonical FACTIONS list first (handles T'au, Emperor's Children, etc.)
 *  Falls back to auto-formatting for any unknown key. */
export function formatFactionName(raw: string): string {
  const faction = FACTION_MAP.get(raw)
  if (faction) return faction.displayName
  // Fallback for unknown keys
  return raw
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}
