export type FactionGroup = 'Imperium' | 'Chaos' | 'Xenos'

export interface Faction {
  key: string
  displayName: string
  color: string
  avgPointsPerModel: number
  group: FactionGroup
}

export const FACTIONS: Faction[] = [
  // ── IMPERIUM ─────────────────────────────────────────────────────
  { key: 'space_marines',     displayName: 'Space Marines',       color: '#3b82f6', avgPointsPerModel: 30,  group: 'Imperium' },
  { key: 'blood_angels',      displayName: 'Blood Angels',        color: '#dc2626', avgPointsPerModel: 32,  group: 'Imperium' },
  { key: 'dark_angels',       displayName: 'Dark Angels',         color: '#15803d', avgPointsPerModel: 30,  group: 'Imperium' },
  { key: 'space_wolves',      displayName: 'Space Wolves',        color: '#7dd3fc', avgPointsPerModel: 30,  group: 'Imperium' },
  { key: 'black_templars',    displayName: 'Black Templars',      color: '#a8a29e', avgPointsPerModel: 28,  group: 'Imperium' },
  { key: 'deathwatch',        displayName: 'Deathwatch',          color: '#475569', avgPointsPerModel: 35,  group: 'Imperium' },
  { key: 'grey_knights',      displayName: 'Grey Knights',        color: '#94a3b8', avgPointsPerModel: 35,  group: 'Imperium' },
  { key: 'adeptus_mechanicus',displayName: 'Adeptus Mechanicus',  color: '#ef4444', avgPointsPerModel: 18,  group: 'Imperium' },
  { key: 'astra_militarum',   displayName: 'Astra Militarum',     color: '#84cc16', avgPointsPerModel: 8,   group: 'Imperium' },
  { key: 'adeptus_custodes',  displayName: 'Adeptus Custodes',    color: '#f59e0b', avgPointsPerModel: 50,  group: 'Imperium' },
  { key: 'adepta_sororitas',  displayName: 'Adepta Sororitas',    color: '#fb7185', avgPointsPerModel: 16,  group: 'Imperium' },
  { key: 'imperial_knights',  displayName: 'Imperial Knights',    color: '#d97706', avgPointsPerModel: 150, group: 'Imperium' },
  { key: 'imperial_agents',   displayName: 'Imperial Agents',     color: '#6366f1', avgPointsPerModel: 20,  group: 'Imperium' },

  // ── CHAOS ─────────────────────────────────────────────────────────
  { key: 'chaos_space_marines', displayName: 'Chaos Space Marines', color: '#991b1b', avgPointsPerModel: 28,  group: 'Chaos' },
  { key: 'death_guard',         displayName: 'Death Guard',          color: '#65a30d', avgPointsPerModel: 32,  group: 'Chaos' },
  { key: 'thousand_sons',       displayName: 'Thousand Sons',        color: '#2563eb', avgPointsPerModel: 28,  group: 'Chaos' },
  { key: 'world_eaters',        displayName: 'World Eaters',         color: '#7f1d1d', avgPointsPerModel: 25,  group: 'Chaos' },
  { key: 'emperors_children',   displayName: "Emperor's Children",   color: '#c026d3', avgPointsPerModel: 26,  group: 'Chaos' },
  { key: 'chaos_daemons',       displayName: 'Chaos Daemons',        color: '#9333ea', avgPointsPerModel: 15,  group: 'Chaos' },
  { key: 'chaos_knights',       displayName: 'Chaos Knights',        color: '#78716c', avgPointsPerModel: 150, group: 'Chaos' },

  // ── XENOS ─────────────────────────────────────────────────────────
  { key: 'orks',               displayName: 'Orks',                color: '#22c55e', avgPointsPerModel: 10,  group: 'Xenos' },
  { key: 'craftworld_aeldari', displayName: 'Craftworld Aeldari',  color: '#a855f7', avgPointsPerModel: 25,  group: 'Xenos' },
  { key: 'drukhari',           displayName: 'Drukhari',            color: '#9d174d', avgPointsPerModel: 12,  group: 'Xenos' },
  { key: 'harlequins',         displayName: 'Harlequins',          color: '#f97316', avgPointsPerModel: 20,  group: 'Xenos' },
  { key: 'ynnari',             displayName: 'Ynnari',              color: '#e879f9', avgPointsPerModel: 25,  group: 'Xenos' },
  { key: 'tau_empire',         displayName: "T'au Empire",         color: '#0ea5e9', avgPointsPerModel: 15,  group: 'Xenos' },
  { key: 'tyranids',           displayName: 'Tyranids',            color: '#a16207', avgPointsPerModel: 22,  group: 'Xenos' },
  { key: 'genestealer_cults',  displayName: 'Genestealer Cults',   color: '#4c1d95', avgPointsPerModel: 12,  group: 'Xenos' },
  { key: 'necrons',            displayName: 'Necrons',             color: '#22d3ee', avgPointsPerModel: 20,  group: 'Xenos' },
  { key: 'leagues_of_votann', displayName: 'Leagues of Votann',   color: '#92400e', avgPointsPerModel: 20,  group: 'Xenos' },
]

export const FACTION_MAP = new Map(FACTIONS.map(f => [f.key, f]))

export function getPointsPerModel(factionKey: string): number {
  return FACTION_MAP.get(factionKey)?.avgPointsPerModel ?? 20
}

export function getFactionColor(factionKey: string): string {
  return FACTION_MAP.get(factionKey)?.color ?? '#60a5fa'
}

export function getFactionDisplayName(factionKey: string): string {
  return FACTION_MAP.get(factionKey)?.displayName ?? factionKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
