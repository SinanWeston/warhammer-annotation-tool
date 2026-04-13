import type { ArmySuggestion } from '../types/army'

export const ARMY_SUGGESTIONS: ArmySuggestion[] = [
  // ── SPACE MARINES ──────────────────────────────────────────
  {
    id: 'sm-aggressive',
    title: 'Assault Spearhead',
    description: 'A melee-heavy Space Marines list built around Bladeguard Veterans and Assault Intercessors. Fast, hard-hitting, designed to control the mid-board.',
    playstyle: 'aggressive',
    faction: 'space_marines',
    suggestedUnits: [
      { unitName: 'Captain', count: 1, reason: 'Aura buffs for melee units' },
      { unitName: 'Chaplain', count: 1, reason: 'Litanies boost charge and melee damage' },
      { unitName: 'Assault Intercessors', count: 10, reason: 'Battleline that wants to be in combat' },
      { unitName: 'Bladeguard Veterans', count: 6, reason: 'Durable melee elite with storm shields' },
      { unitName: 'Inceptor Squad', count: 6, reason: 'Deep strike pressure and fire support' },
      { unitName: 'Redemptor Dreadnought', count: 1, reason: 'Anchor piece — tough and shooty' },
    ],
    totalPoints: 935,
  },
  {
    id: 'sm-balanced',
    title: 'Gladius Task Force',
    description: 'A well-rounded Space Marines list with shooting, melee, and durable objective holders.',
    playstyle: 'balanced',
    faction: 'space_marines',
    suggestedUnits: [
      { unitName: 'Captain', count: 1, reason: 'Versatile leader' },
      { unitName: 'Lieutenant', count: 1, reason: 'Wound re-rolls for shooting' },
      { unitName: 'Intercessors', count: 10, reason: 'Solid battleline for objectives' },
      { unitName: 'Hellblaster Squad', count: 5, reason: 'Anti-elite firepower' },
      { unitName: 'Eradicator Squad', count: 3, reason: 'Anti-vehicle specialists' },
      { unitName: 'Redemptor Dreadnought', count: 1, reason: 'Versatile heavy support' },
      { unitName: 'Outrider Squad', count: 3, reason: 'Fast objective grabbers' },
    ],
    totalPoints: 960,
  },
  {
    id: 'sm-competitive',
    title: 'Ironstorm Gunline',
    description: 'Competitive Space Marines list focused on long-range firepower and armored threats.',
    playstyle: 'competitive',
    faction: 'space_marines',
    suggestedUnits: [
      { unitName: 'Techmarine', count: 1, reason: 'Vehicle repair and buffs' },
      { unitName: 'Intercessors', count: 5, reason: 'Minimum battleline' },
      { unitName: 'Eradicator Squad', count: 6, reason: 'Melta firepower' },
      { unitName: 'Redemptor Dreadnought', count: 1, reason: 'Core vehicle threat' },
      { unitName: 'Gladiator Lancer', count: 1, reason: 'Long-range anti-tank' },
      { unitName: 'Hellblaster Squad', count: 10, reason: 'Volume plasma shooting' },
    ],
    totalPoints: 970,
  },

  // ── NECRONS ────────────────────────────────────────────────
  {
    id: 'nec-defensive',
    title: 'Living Metal Wall',
    description: 'Durable Necrons list that grinds opponents down with Reanimation Protocols and tough units.',
    playstyle: 'defensive',
    faction: 'necrons',
    suggestedUnits: [
      { unitName: 'Overlord', count: 1, reason: 'Command Protocols and buffs' },
      { unitName: 'Technomancer', count: 1, reason: 'Enhanced reanimation' },
      { unitName: 'Necron Warriors', count: 20, reason: 'Hordes that keep coming back' },
      { unitName: 'Lychguard', count: 5, reason: 'Elite bodyguard with shields' },
      { unitName: 'Canoptek Wraiths', count: 3, reason: 'Counter-assault with invulnerable save' },
      { unitName: 'Doomsday Ark', count: 1, reason: 'Long-range fire support' },
    ],
    totalPoints: 845,
  },
  {
    id: 'nec-aggressive',
    title: 'Destroyer Cult',
    description: 'Aggressive Necrons built around Skorpekh Destroyers and fast flanking units.',
    playstyle: 'aggressive',
    faction: 'necrons',
    suggestedUnits: [
      { unitName: 'Overlord', count: 1, reason: 'My Will Be Done for hit re-rolls' },
      { unitName: 'Skorpekh Destroyers', count: 6, reason: 'Core melee threat' },
      { unitName: 'Canoptek Wraiths', count: 6, reason: 'Fast, tough flankers' },
      { unitName: 'Immortals', count: 10, reason: 'Mobile fire support' },
      { unitName: 'Tomb Blades', count: 3, reason: 'Fast objective grabbers' },
    ],
    totalPoints: 770,
  },

  // ── ORKS ───────────────────────────────────────────────────
  {
    id: 'ork-aggressive',
    title: 'WAAAGH! Stampede',
    description: 'Maximum Ork aggression. Floods the board with bodies and charges everything.',
    playstyle: 'aggressive',
    faction: 'orks',
    suggestedUnits: [
      { unitName: 'Warboss', count: 1, reason: 'WAAAGH! calls and melee beast' },
      { unitName: 'Weirdboy', count: 1, reason: 'Da Jump to teleport Boyz' },
      { unitName: 'Boyz', count: 20, reason: 'Wall of green muscle' },
      { unitName: 'Beast Snagga Boyz', count: 10, reason: 'Anti-vehicle melee troops' },
      { unitName: 'Meganobz', count: 3, reason: 'Heavy melee punch' },
      { unitName: 'Stormboyz', count: 10, reason: 'Fast assault infantry' },
    ],
    totalPoints: 605,
  },

  // ── T'AU EMPIRE ────────────────────────────────────────────
  {
    id: 'tau-defensive',
    title: 'Mont\'ka Gunline',
    description: 'Classic T\'au shooting castle with overlapping fire lanes and drone support.',
    playstyle: 'defensive',
    faction: 'tau_empire',
    suggestedUnits: [
      { unitName: 'Commander in Coldstar', count: 1, reason: 'Mobile fire platform' },
      { unitName: 'Cadre Fireblade', count: 1, reason: 'Extra shots for Strike Teams' },
      { unitName: 'Strike Team', count: 10, reason: 'Core fire warriors' },
      { unitName: 'Crisis Battlesuits', count: 6, reason: 'Flexible loadout platform' },
      { unitName: 'Broadside Battlesuits', count: 3, reason: 'Anti-vehicle railguns' },
      { unitName: 'Riptide Battlesuit', count: 1, reason: 'Centerpiece heavy hitter' },
    ],
    totalPoints: 895,
  },

  // ── TYRANIDS ───────────────────────────────────────────────
  {
    id: 'nid-balanced',
    title: 'Synaptic Swarm',
    description: 'Balanced Tyranids with screening gaunts, synapse support, and heavy hitters.',
    playstyle: 'balanced',
    faction: 'tyranids',
    suggestedUnits: [
      { unitName: 'Hive Tyrant', count: 1, reason: 'Synapse leader and monster' },
      { unitName: 'Neurothrope', count: 1, reason: 'Psychic support and synapse' },
      { unitName: 'Termagants', count: 20, reason: 'Screening and objective bodies' },
      { unitName: 'Warriors', count: 3, reason: 'Synapse and fire support' },
      { unitName: 'Zoanthropes', count: 3, reason: 'Psychic devastation' },
      { unitName: 'Carnifex', count: 2, reason: 'Wrecking ball monsters' },
    ],
    totalPoints: 860,
  },

  // ── ADEPTUS CUSTODES ───────────────────────────────────────
  {
    id: 'cust-competitive',
    title: 'Golden Host',
    description: 'Elite Custodes list — few models, each a one-man army. Every model matters.',
    playstyle: 'competitive',
    faction: 'adeptus_custodes',
    suggestedUnits: [
      { unitName: 'Shield-Captain', count: 1, reason: 'Tanky leader with 4++ invuln' },
      { unitName: 'Blade Champion', count: 1, reason: 'Character assassin' },
      { unitName: 'Custodian Guard', count: 6, reason: 'Core battleline, extremely durable' },
      { unitName: 'Allarus Terminators', count: 3, reason: 'Deep strike threats' },
      { unitName: 'Vertus Praetors', count: 3, reason: 'Fast bikes with hurricane bolters' },
    ],
    totalPoints: 820,
  },

  // ── ASTRA MILITARUM ────────────────────────────────────────
  {
    id: 'am-balanced',
    title: 'Cadian Combined Arms',
    description: 'Classic Guard — infantry screens backed by tanks. Volume of fire and armor.',
    playstyle: 'balanced',
    faction: 'astra_militarum',
    suggestedUnits: [
      { unitName: 'Company Commander', count: 1, reason: 'Orders for infantry' },
      { unitName: 'Tank Commander', count: 1, reason: 'Tank ace with BS3+' },
      { unitName: 'Cadian Shock Troops', count: 10, reason: 'Backbone infantry' },
      { unitName: 'Infantry Squad', count: 10, reason: 'Screening and objectives' },
      { unitName: 'Kasrkin', count: 10, reason: 'Elite special weapons team' },
      { unitName: 'Leman Russ Battle Tank', count: 1, reason: 'Durable multi-role tank' },
      { unitName: 'Sentinel', count: 2, reason: 'Cheap scout deployment' },
    ],
    totalPoints: 700,
  },
]
