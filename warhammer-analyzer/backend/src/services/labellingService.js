/**
 * Labelling Service — v2 only.
 *
 * Reads crops from the unified `data/labels.csv` (v2 schema). Supports
 * filtering by source (cmon | annotation | gw_shop | …) and enriches CMON
 * rows with context pulled from
 * `scripts/cmon/images/<run>/<id>/manifest.json`.
 *
 * The v1 walker (scripts/phase1/crops/) was retired in the 2026-04 audit
 * sweep; callers that still operate on raw crop directories should populate
 * labels.csv first.
 *
 * All IO scoped to configured paths — no arbitrary-path access. CSV-derived
 * paths are asserted to stay inside `cropsRepoRoot`, and CMON scene paths
 * inside `cmonRoot`, so a corrupt or adversarial row cannot coerce the
 * server into serving arbitrary files.
 */

import fs from 'node:fs/promises'
import path from 'node:path'
import { createHash } from 'node:crypto'
import sharp from 'sharp'
import { getLabellingConfig, createProvider } from '../config/pipeline.js'
import { logger } from '../utils/logger.js'
import {
  readLabelsCsv,
  writeLabelsCsv,
  updateLabelRow,
  utcNowIso,
  V2_COLUMNS,
  mergeColumns,
  withCsvLock,
} from './labelsCsvService.js'

// ── path resolution ────────────────────────────────────────────────────────
/** Resolve a config-relative path against the warhammer-analyzer CWD. */
function resolveLabellingPath(configPath) {
  return path.resolve(process.cwd(), configPath)
}

/** Assert that `abs` lives inside `root`. Throws a 400 if not — blocks
 *  `crop_path = "../../etc/passwd"` style escapes out of the intended tree.
 *  Exact match of the root itself is allowed (resolving `.` against root). */
function assertInsideRoot(abs, root) {
  const rootResolved = path.resolve(root)
  if (abs === rootResolved) return
  if (!abs.startsWith(rootResolved + path.sep)) {
    const err = new Error(`path escape: ${abs} is outside ${rootResolved}`)
    err.status = 400
    throw err
  }
}

/** Resolve a `crop_path` field from labels.csv against the repo root and
 *  assert it stays inside — CSV rows are trusted-ish, but a corrupt or
 *  adversarial row should not be able to coerce the server into serving
 *  arbitrary files.
 */
function resolveCropPathFromCsv(cropPath) {
  const cfg = getLabellingConfig()
  const repoRoot = resolveLabellingPath(cfg.cropsRepoRoot)
  const abs = path.resolve(repoRoot, cropPath)
  assertInsideRoot(abs, repoRoot)
  return abs
}

/** CMON entry ids are numeric-ish slugs from the scraper (e.g. `475293`,
 *  `1010049_f5e565dab33c`). Anything outside `[A-Za-z0-9_-]` is either a
 *  bug or an attempt to traverse into another directory. */
function assertValidEntryId(entryId) {
  if (typeof entryId !== 'string' || !/^[A-Za-z0-9_-]+$/.test(entryId)) {
    const err = new Error(`invalid entry id: ${entryId}`)
    err.status = 400
    throw err
  }
}

// ── id derivation ──────────────────────────────────────────────────────────
/** Build a stable crop ID from its repo-relative crop_path. MD5 first 12 chars. */
function cropIdFromPath(cropPath) {
  return createHash('md5').update(cropPath).digest('hex').slice(0, 12)
}

// ── cheatsheet (unchanged from v1) ─────────────────────────────────────────
let _cheatsheetByFaction = null

async function loadCheatsheet() {
  if (_cheatsheetByFaction) return _cheatsheetByFaction
  const cfg = getLabellingConfig()
  const p = resolveLabellingPath(cfg.cheatsheet)
  let text
  try {
    text = await fs.readFile(p, 'utf8')
  } catch (err) {
    logger.warn(`Cheatsheet not found at ${p}; labelling will run without allowed-unit scoping`)
    _cheatsheetByFaction = new Map()
    return _cheatsheetByFaction
  }
  const map = new Map()
  let currentFaction = null
  for (const line of text.split('\n')) {
    const headerMatch = line.match(/^##\s+([a-z0-9_]+)/i)
    if (headerMatch) {
      currentFaction = headerMatch[1]
      if (!map.has(currentFaction)) map.set(currentFaction, [])
      continue
    }
    const slugMatch = line.match(/^\s*-\s*`([a-z0-9_]+)`/i)
    if (slugMatch && currentFaction) {
      map.get(currentFaction).push(slugMatch[1])
    }
  }
  _cheatsheetByFaction = map
  return map
}

// ── units.json (for faction list + slug → faction resolution) ──────────────
let _unitsData = null

async function loadUnits() {
  if (_unitsData) return _unitsData
  const cfg = getLabellingConfig()
  const p = resolveLabellingPath(cfg.unitsJson)
  try {
    const text = await fs.readFile(p, 'utf8')
    _unitsData = JSON.parse(text)
  } catch (err) {
    logger.warn(`units.json not found at ${p}: ${err.message}`)
    _unitsData = { factions: {} }
  }
  return _unitsData
}

/** Return the canonical 20-faction slug list (matching photoanalyzer.taxonomy). */
export async function listFactions() {
  const units = await loadUnits()
  return Object.keys(units.factions || {})
}

/** Slugify helper — must match photoanalyzer.taxonomy.slugify exactly, including
 *  Unicode curly-quote handling. Single source of truth: both `listUnitsForFaction`
 *  and `buildSlugToFactions` go through this so a unit like "Be'lakor" or
 *  "Rune Priest" produces the same slug in every call site.
 */
export function slugifyName(name) {
  return String(name || '')
    .toLowerCase()
    .replace(/\u2018/g, '')  // ‘
    .replace(/\u2019/g, '')  // ’
    .replace(/'/g, '')
    .replace(/ /g, '_')
}

/** Return every unit in a faction as `{slug, name, category, chapter, role}`.
 *  Used by the typeahead picker. Faction aliases resolve to their canonical form.
 */
export async function listUnitsForFaction(faction) {
  const units = await loadUnits()
  // Resolve alias (simple mapping — the full alias map lives in Python, but
  // for the UI we only need to handle the 20 canonical factions that the
  // picker offers).
  const body = units.factions?.[faction]
  if (!body) return []
  return (body.units || []).map((u) => ({
    slug: slugifyName(u.name),
    name: u.name,
    category: u.category || '',
    chapter: u.chapter || '',
    role: u.role || '',
  }))
}

/** Faction aliases: non-canonical slug → canonical faction. Mirrors the
 *  Python source of truth at `src/photoanalyzer/taxonomy.py:FACTION_ALIASES`.
 *  Keep these two tables in lockstep — if Python and Node disagree on an
 *  alias, a row written by one side gets rejected by the other's validator.
 *  TODO: factor into a shared JSON at scripts/data/faction_aliases.json.
 */
const FACTION_ALIASES = Object.freeze({
  // Loyalist space marine chapters (collapsed for the coarse classifier)
  blood_angels:      'space_marines',
  dark_angels:       'space_marines',
  space_wolves:      'space_marines',
  black_templars:    'space_marines',
  ultramarines:      'space_marines',
  crimson_fists:     'space_marines',
  imperial_fists:    'space_marines',
  salamanders:       'space_marines',
  iron_hands:        'space_marines',
  raven_guard:       'space_marines',
  white_scars:       'space_marines',
  chapter_marines:   'space_marines',
  primaris:          'space_marines',
  deathwatch:        'space_marines',
  grey_knights:      'space_marines',
  // Chaos sub-factions (10th ed standalone books; collapsed for classifier)
  death_guard:       'chaos_space_marines',
  thousand_sons:     'chaos_space_marines',
  world_eaters:      'chaos_space_marines',
  emperors_children: 'chaos_space_marines',
  // Historical / short / alt forms
  imperial_guard:    'astra_militarum',
  eldar:             'aeldari',
  craftworlds:       'aeldari',
  dark_eldar:        'drukhari',
  custodes:          'adeptus_custodes',
  mechanicus:        'adeptus_mechanicus',
  sororitas:         'adepta_sororitas',
  sisters_of_battle: 'adepta_sororitas',
  genestealer_cult:  'genestealer_cults',
  tau:               'tau_empire',
  votann:            'leagues_of_votann',
})

/** Module-level cache for the canonical faction set so every saveLabel /
 *  editCropBbox call doesn't hit loadUnits() just to build a Set. Populated
 *  lazily on first call. Keep it as a Promise so concurrent first-callers
 *  share one build. */
let _canonicalFactionsPromise = null

async function getCanonicalFactions() {
  if (!_canonicalFactionsPromise) {
    _canonicalFactionsPromise = (async () => {
      const units = await loadUnits()
      return new Set(Object.keys(units.factions || {}))
    })()
  }
  return _canonicalFactionsPromise
}

/** Resolve a user-supplied faction value to its canonical form.
 *  Returns:
 *    - the same string if it's already canonical
 *    - the canonical slug if `raw` is in FACTION_ALIASES
 *    - null if it's neither (caller should 400 on null)
 *  Does NOT throw — callers decide the severity. */
export async function resolveFaction(raw) {
  if (typeof raw !== 'string') return null
  const v = raw.trim()
  if (!v) return null
  const canon = await getCanonicalFactions()
  if (canon.has(v)) return v
  const aliased = FACTION_ALIASES[v]
  if (aliased && canon.has(aliased)) return aliased
  return null
}

/** Throw a 400 if `raw` is non-empty and doesn't resolve. Returns the
 *  canonical slug on success (so callers can auto-normalise). Empty input
 *  is allowed — callers that require a faction should check separately. */
export async function assertValidFaction(raw) {
  if (raw === undefined || raw === null || String(raw).trim() === '') return ''
  const canonical = await resolveFaction(raw)
  if (!canonical) {
    const canon = await getCanonicalFactions()
    const err = new Error(
      `Unknown faction '${raw}'. Valid canonical factions: ${[...canon].sort().join(', ')}.`
    )
    err.status = 400
    throw err
  }
  return canonical
}

/** slug → [faction, …] mapping (unique if unambiguous, otherwise multi-element).
 *  Uses the canonical `slugifyName` so curly-quote / apostrophe handling matches
 *  everywhere else — previously this inlined a reduced slugifier that missed
 *  `\u2018/\u2019`, which caused faction auto-resolve to silently fail on any
 *  unit with a typographic quote. */
async function buildSlugToFactions() {
  const units = await loadUnits()
  const map = new Map() // slug → Set<faction>
  for (const [faction, body] of Object.entries(units.factions || {})) {
    for (const u of body.units || []) {
      const slug = slugifyName(u.name)
      if (!slug) continue
      if (!map.has(slug)) map.set(slug, new Set())
      map.get(slug).add(faction)
    }
  }
  return map
}

// ── CMON manifest cache ────────────────────────────────────────────────────
const _cmonManifestCache = new Map() // entry_id → manifest object | null

async function loadCmonManifest(entryId) {
  if (_cmonManifestCache.has(entryId)) return _cmonManifestCache.get(entryId)
  assertValidEntryId(entryId)
  const cfg = getLabellingConfig()
  const cmonRoot = resolveLabellingPath(cfg.cmonRoot)
  // Try each run dir until we find one
  const runsDir = path.join(cmonRoot, 'images')
  let runs = []
  try { runs = await fs.readdir(runsDir) } catch { runs = [] }
  for (const run of runs) {
    const mp = path.join(runsDir, run, entryId, 'manifest.json')
    try {
      const text = await fs.readFile(mp, 'utf8')
      const m = JSON.parse(text)
      _cmonManifestCache.set(entryId, m)
      return m
    } catch (err) {
      if (err.code !== 'ENOENT') logger.warn(`CMON manifest read failed ${mp}: ${err.message}`)
    }
  }
  _cmonManifestCache.set(entryId, null)
  return null
}

// ── CMON category (single / squad / …) ────────────────────────────────────
// Labelling queue order: single-mini scenes are the cleanest to label, so the
// UI sees them first, then squads, busts, dioramas, terrain, and finally
// anything we couldn't categorise. Within a category we sort by faction so
// related units batch together.

const CATEGORY_RANK = {
  single: 0,
  squad: 1,
  bust: 2,
  diorama: 3,
  terrain: 4,
  unknown: 5,
}

const TYPE_TAG_TO_CATEGORY = new Map([
  ['Single', 'single'],
  ['Squad', 'squad'],
  ['Bust', 'bust'],
  ['Diorama', 'diorama'],
  ['Terrain', 'terrain'],
])

// CMON `type_id` enumeration, per scripts/cmon/targeting.json.
const TYPE_ID_TO_CATEGORY = { 1: 'single', 2: 'squad', 3: 'diorama', 4: 'terrain', 5: 'bust' }

/** Derive a category from a CMON manifest/entry object. Returns null on miss. */
function categoryFromManifest(manifest) {
  if (!manifest) return null
  for (const t of manifest.tags || []) {
    const c = TYPE_TAG_TO_CATEGORY.get(t)
    if (c) return c
  }
  if (manifest.type_id != null && TYPE_ID_TO_CATEGORY[manifest.type_id]) {
    return TYPE_ID_TO_CATEGORY[manifest.type_id]
  }
  return null
}

// Fallback source: the `all`-run per-instance manifest often drops the type
// tag, but the source scrape jsonl keeps it. Parse both files once, cache the
// entry_id → category map.
let _cmonEntriesIndex = null

async function loadCmonEntriesIndex() {
  if (_cmonEntriesIndex) return _cmonEntriesIndex
  const cfg = getLabellingConfig()
  const cmonRoot = resolveLabellingPath(cfg.cmonRoot)
  const files = ['entries_all.jsonl', 'entries_single.jsonl']
  const map = new Map()
  for (const f of files) {
    const p = path.join(cmonRoot, 'data', f)
    let text = ''
    try {
      text = await fs.readFile(p, 'utf8')
    } catch (err) {
      if (err.code !== 'ENOENT') logger.warn(`CMON entries read failed ${p}: ${err.message}`)
      continue
    }
    for (const line of text.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed) continue
      try {
        const d = JSON.parse(trimmed)
        const cat = categoryFromManifest(d)
        if (d.id && cat && !map.has(d.id)) map.set(d.id, cat)
      } catch {
        // ignore malformed lines
      }
    }
  }
  _cmonEntriesIndex = map
  return map
}

async function resolveCmonCategory(instanceId) {
  if (!instanceId || !instanceId.startsWith('cmon:')) return 'unknown'
  const entryId = instanceId.slice(5)
  const fromManifest = categoryFromManifest(await loadCmonManifest(entryId))
  if (fromManifest) return fromManifest
  const idx = await loadCmonEntriesIndex()
  return idx.get(entryId) || 'unknown'
}

/** Non-CMON sources don't carry scene-type metadata. Annotation crops are
 *  bbox-cut individual miniatures, and gw_shop / Warhammer Community images
 *  are per-unit product shots — both behave as single-mini scenes for
 *  labelling priority. Everything else is 'unknown' until categorised. */
function categoryForNonCmon(source) {
  if (source === 'annotation' || source === 'gw_shop') return 'single'
  return 'unknown'
}

async function resolveCategoryForRow(row) {
  if (row.source === 'cmon') return resolveCmonCategory(row.instance_id || '')
  return categoryForNonCmon(row.source)
}

/** Resolve the absolute filesystem path of the original CMON scene image for a
 *  given (instance_id, view_idx). Returns null if unknown.
 *
 *  Hardened: the entry id must match the CMON scraper's slug shape, and the
 *  resolved file must live under `cmonRoot`. Absolute `local_paths` are
 *  rejected — manifests should always store relative paths. This blocks
 *  `manifest.local_paths = ["/etc/passwd"]` escapes. */
export async function resolveSceneImagePath(instanceId, viewIdx) {
  if (!instanceId || !instanceId.startsWith('cmon:')) return null
  const entryId = instanceId.slice(5)
  assertValidEntryId(entryId)
  const manifest = await loadCmonManifest(entryId)
  if (!manifest) return null
  const rel = (manifest.local_paths || [])[viewIdx]
  if (!rel) return null
  const cfg = getLabellingConfig()
  const cmonRoot = resolveLabellingPath(cfg.cmonRoot)
  if (path.isAbsolute(rel)) {
    logger.warn(`manifest ${entryId} has absolute local_path ${rel} — rejecting`)
    return null
  }
  const abs = path.resolve(cmonRoot, rel)
  assertInsideRoot(abs, cmonRoot)
  return abs
}

/** Build the `context` object for a CMON crop row. Returns null for non-CMON. */
async function buildContextForRow(row, siblingsByInstance) {
  if (row.source !== 'cmon') return null
  const instance = row.instance_id || ''
  const entryId = instance.startsWith('cmon:') ? instance.slice(5) : ''
  if (!entryId) return null
  const manifest = await loadCmonManifest(entryId)
  if (!manifest) return null

  const siblings = siblingsByInstance.get(instance) || []
  // Filter out this exact row from the siblings list (same crop_path)
  const siblingsOther = siblings.filter((s) => s.crop_path !== row.crop_path)

  const viewIdx = row.view_idx !== '' && row.view_idx !== null
    ? parseInt(row.view_idx, 10)
    : 0

  return {
    source_url: manifest.url || `https://www.coolminiornot.com/${entryId}`,
    title: manifest.title || manifest.tile_title || '',
    description: manifest.description || '',
    artist: manifest.artist || manifest.tile_artist || '',
    score: manifest.score ?? null,
    votes: manifest.votes ?? null,
    tags: manifest.tags || [],
    sibling_count: siblingsOther.length,  // count of OTHER crops in this instance
    siblings: siblingsOther.map((s) => ({
      id: s.id,
      view_idx: s.view_idx,
      labelled: s.labelled,
      unit_slug: s.unit_slug,
    })),
    scene_url: `/api/labelling/scenes/${encodeURIComponent(instance)}/${viewIdx}/image`,
    scene_source: manifest.image_urls?.[viewIdx] || '',  // original CMON URL (for "open original")
    // Total number of source photos in the CMON entry — may exceed the
    // sibling count because the detector can emit 0 boxes on some photos,
    // which leaves those views without any crop rows. The redraw modal uses
    // this to show a tab per photo, not per existing crop.
    total_views: (manifest.local_paths || []).length,
  }
}

// ── v2 reader path ─────────────────────────────────────────────────────────
async function listCropsV2({ sourceFilter, unlabelledOnly, auditOnly, limit, withContext } = {}) {
  const cfg = getLabellingConfig()
  const csvPath = resolveLabellingPath(cfg.labelsCsvV2)
  const { rows } = await readLabelsCsv(csvPath)

  // Pre-compute sibling info by instance_id — the context panel needs this
  // to render the sibling ribbon + "copy to all N siblings" button.
  // EXCLUDE sentinel rows (__bad_crop__ / __unknown__ / __ambiguous__) —
  // those have been retired; showing them as siblings just inflates the
  // count after every redraw (every bad-marked crop would forever stick
  // around in the ribbon, and new redraws would pile on top).
  const siblingsByInstance = new Map()  // instance_id → [{id, crop_path, view_idx, labelled, unit_slug}]
  for (const r of rows) {
    const iid = r.instance_id
    if (!iid) continue
    const slug = r.unit_slug || ''
    if (slug.startsWith('__') && slug.endsWith('__')) continue   // sentinel — skip
    if (!siblingsByInstance.has(iid)) siblingsByInstance.set(iid, [])
    const humanConf = r.suggested_by === 'human' || !!r.labeller
    siblingsByInstance.get(iid).push({
      id: cropIdFromPath(r.crop_path),
      crop_path: r.crop_path,
      view_idx: r.view_idx === '' ? null : Number(r.view_idx),
      labelled: humanConf,
      unit_slug: slug,
    })
  }

  const sources = sourceFilter
    ? new Set((Array.isArray(sourceFilter) ? sourceFilter : sourceFilter.split(',')).map((s) => s.trim()))
    : null

  // Build the candidate list first (filter only — no context, no limit).
  // Context is expensive on the hot path; we defer it until after sort+slice.
  const candidates = []
  for (const r of rows) {
    if (sources && !sources.has(r.source)) continue
    // "labelled" in the UI sense = human has confirmed. Weak-sup / LLM
    // pre-filled rows (suggested_by="weak_regex:*" or "llm:*") still need
    // human confirmation, so they stay in the unlabelled queue until saved.
    const humanConfirmed = r.suggested_by === 'human' || !!r.labeller
    const labelled = humanConfirmed
    const isAuditRow =
      humanConfirmed &&
      (r.unit_slug || '') === '' &&
      /\bflag:audit\b/.test(r.notes || '')
    if (auditOnly) {
      // Audit pile = rows the user deferred, not the full unlabelled queue.
      if (!isAuditRow) continue
    } else if (unlabelledOnly) {
      // Unlabelled queue hides labelled rows BUT keeps audit-flagged rows
      // out too (they were intentionally deferred — don't re-queue them).
      if (labelled) continue
    }
    const cropPath = r.crop_path
    const id = cropIdFromPath(cropPath)
    const item = {
      id,
      crop_path: cropPath,
      source: r.source || '',
      source_ref: r.source_ref || '',
      instance_id: r.instance_id || '',
      view_idx: r.view_idx === '' ? null : Number(r.view_idx),
      faction: r.faction || '',
      unit_slug: r.unit_slug || '',
      labelled,
      notes: r.notes || '',
      // Scene-type priority for the queue: 'single' → 'squad' → …
      category: 'unknown',
      // Weak-sup / LLM provenance so UI can render trust signals
      suggestion: buildSuggestionMeta(r),
      context: null,
      // Legacy shape (kept for back-compat while v2 UI rolls out)
      filename: path.basename(cropPath),
      relPath: cropPath,
      labelKey: cropPath,
    }
    candidates.push({ item, row: r })
  }

  // Annotate every candidate with its category (uses cached manifest reads
  // for CMON; constant time for other sources).
  await Promise.all(candidates.map(async ({ item, row }) => {
    item.category = await resolveCategoryForRow(row)
  }))

  // Sort: single → squad → bust → diorama → terrain → unknown,
  // then faction (empty factions last), then crop_path for stable ordering.
  candidates.sort((a, b) => {
    const ra = CATEGORY_RANK[a.item.category] ?? CATEGORY_RANK.unknown
    const rb = CATEGORY_RANK[b.item.category] ?? CATEGORY_RANK.unknown
    if (ra !== rb) return ra - rb
    const fa = a.item.faction || '\uffff'
    const fb = b.item.faction || '\uffff'
    if (fa !== fb) return fa.localeCompare(fb)
    return a.item.crop_path.localeCompare(b.item.crop_path)
  })

  const selected = limit ? candidates.slice(0, limit) : candidates

  // Compute context only for the selected slice.
  if (withContext) {
    await Promise.all(selected.map(async ({ item, row }) => {
      item.context = await buildContextForRow(row, siblingsByInstance)
    }))
  }

  return selected.map(({ item }) => item)
}

/** Extract suggestion metadata from a labels.csv row. Returns null when no
 *  machine suggestion exists (human-confirmed rows or pristine empty rows). */
function buildSuggestionMeta(row) {
  const by = row.suggested_by || ''
  if (!by || by === 'human') return null
  // by looks like "weak_regex:char_table" or "llm:claude-sonnet-4-5"
  const [kind, origin] = by.includes(':') ? by.split(':', 2) : [by, '']
  const confRaw = row.confidence
  const conf = confRaw ? parseFloat(confRaw) : null
  // Notes often carry the weak-sup rule that fired (e.g. "weak:char:magnus_the_red")
  // — surface it so the UI can show *why* this was suggested.
  const noteMatch = /\bweak:([^;]+)/.exec(row.notes || '')
  const rule = noteMatch ? noteMatch[1].trim() : ''
  const flagMatch = /\bflag:([^;]+)/.exec(row.notes || '')
  return {
    kind,              // "weak_regex" | "llm"
    origin,            // "char_table" | "faction_kw" | "unit_kw" | "auto_unique_unit" | etc.
    confidence: conf,  // 0..1 or null
    rule,              // e.g. "char:magnus_the_red" or "auto:rubric_marines"
    flag: flagMatch ? flagMatch[1].trim() : '',  // e.g. "title_detector_conflict"
    detector_faction: (/detector_faction=([a-z0-9_]+)/.exec(row.notes || '') || [])[1] || '',
    detector_conf: parseFloat((/detector_conf=([\d.]+)/.exec(row.notes || '') || [])[1] || '0') || null,
  }
}

async function resolveCropFromV2(id) {
  const cfg = getLabellingConfig()
  const csvPath = resolveLabellingPath(cfg.labelsCsvV2)
  const { rows } = await readLabelsCsv(csvPath)
  for (const r of rows) {
    if (cropIdFromPath(r.crop_path) === id) return r
  }
  const err = new Error(`Unknown crop id: ${id}`)
  err.status = 404
  throw err
}

// ── public API ─────────────────────────────────────────────────────────────
/** List crops with labelling status. `opts` supports `sourceFilter`,
 *  `unlabelledOnly`, `limit`, `withContext` (default true).
 *
 *  v1 (scripts/phase1/crops walker) was retired — v2 `data/labels.csv` is the
 *  only supported data source. Legacy callers relying on v1 should populate
 *  labels.csv instead (`scripts/apply_weak_sup.py` or the migration helper). */
export async function listCrops(opts = {}) {
  const withContext = opts.withContext ?? true
  return listCropsV2({ ...opts, withContext })
}

/** Resolve a crop to an on-disk path (absolute). */
export async function resolveCropPath(id) {
  const row = await resolveCropFromV2(id)
  return {
    id,
    crop_path: row.crop_path,
    absPath: resolveCropPathFromCsv(row.crop_path),
    faction: row.faction || '',
    filename: path.basename(row.crop_path),
    source: row.source || '',
    row,
  }
}

/** LLM suggestion for one crop.
 *
 *  The `top` field is the model's best guess. `alternatives` is populated
 *  from the per-faction cheatsheet (not the model response) — the prompt
 *  currently asks for a single classification, not a top-k. Wiring the
 *  model's own alternatives through would require extending CLASSIFY_BASE
 *  + normalizeClassification; tracked as a follow-up. */
export async function suggestForCrop(id, { extraAlternatives = 4 } = {}) {
  const crop = await resolveCropPath(id)
  const cheatsheet = await loadCheatsheet()
  const cfg = getLabellingConfig()

  const factionForPrompt = crop.faction || null  // may be empty on CMON rows
  const allowedUnits = factionForPrompt ? (cheatsheet.get(factionForPrompt) || []) : []
  const cheatsheetText = allowedUnits.length
    ? `For ${factionForPrompt}, valid slugs include: ${allowedUnits.slice(0, 30).join(', ')}${
        allowedUnits.length > 30 ? ', …' : ''
      }.`
    : undefined

  const provider = await createProvider(cfg.suggestProvider, cfg.suggestModel)
  const buffer = await fs.readFile(crop.absPath)

  const t0 = Date.now()
  const primary = await provider.classifyImage(buffer, {
    factionHint: factionForPrompt,
    allowedUnits,
    cheatsheet: cheatsheetText,
  })
  const elapsedMs = Date.now() - t0

  const alternatives = allowedUnits
    .filter((u) => u !== primary.unit)
    .slice(0, extraAlternatives)
    .map((unit) => ({ unit, faction: factionForPrompt, confidence: null, source: 'cheatsheet' }))

  return {
    crop: { id, faction: factionForPrompt || '', filename: crop.filename },
    top: {
      unit: primary.unit,
      faction: primary.faction || factionForPrompt || '',
      confidence: primary.confidence,
      reasoning: primary.reasoning,
      source: 'llm',
    },
    alternatives,
    provider: { name: cfg.suggestProvider, model: cfg.suggestModel },
    elapsedMs,
  }
}

/** Sentinel unit_slugs for non-unit outcomes. These are reserved strings
 *  (start with `__`, can't collide with real slugs) that the gallery builder
 *  filters out. */
const STATUS_SENTINELS = {
  bad_crop: '__bad_crop__',   // detector false positive — not a mini
  unknown: '__unknown__',     // user looked but can't identify
  ambiguous: '__ambiguous__', // multiple valid answers (multi-subject crop)
}

/** Special pseudo-status: "I looked at this but I'm not ready to commit to a
 *  slug yet — come back later." Stores a literal empty unit_slug with a
 *  `flag:audit` marker in notes. Distinct from `unknown` (which claims
 *  "nobody could label this") and from Skip (which doesn't save a row). */
const AUDIT_STATUS = 'audit'
const AUDIT_FLAG = 'flag:audit'

/** Save a label. v2: updates the row in `data/labels.csv` with proper
 *  provenance (suggested_by=human, labeller, created_at). Auto-fills faction
 *  when the chosen slug is unambiguously owned by exactly one faction.
 *
 *  Options:
 *  - `status`: one of 'bad_crop' | 'unknown' | 'ambiguous' — writes a sentinel
 *              slug instead of a real one. `unit_slug` is ignored when given.
 *  - `copy_to_siblings`: if true and the crop has an instance_id, the same
 *              label is applied to every other crop sharing that instance_id.
 */
export async function saveLabel(id, opts = {}) {
  const {
    unit_slug,
    notes = '',
    faction,
    labeller = 'human',
    status,
    copy_to_siblings = false,
  } = opts

  // Resolve the effective slug:
  //  - status='audit' → literal blank (user is deferring the decision)
  //  - other status → sentinel slug (__bad_crop__ / __unknown__ / __ambiguous__)
  //  - no status → user-provided slug (required)
  let effectiveSlug
  let isAudit = false
  if (status === AUDIT_STATUS) {
    effectiveSlug = ''
    isAudit = true
  } else if (status) {
    if (!STATUS_SENTINELS[status]) {
      const err = new Error(
        `Unknown status '${status}'. Must be one of: ${Object.keys(STATUS_SENTINELS).join(', ')}, ${AUDIT_STATUS}`
      )
      err.status = 400; throw err
    }
    effectiveSlug = STATUS_SENTINELS[status]
  } else {
    if (typeof unit_slug !== 'string' || !unit_slug.trim()) {
      const err = new Error('unit_slug or status is required')
      err.status = 400; throw err
    }
    effectiveSlug = unit_slug.trim().toLowerCase()
  }
  const noteText = String(notes || '').trim()

  const cfg = getLabellingConfig()
  const csvPath = resolveLabellingPath(cfg.labelsCsvV2)
  return withCsvLock(csvPath, async () => {
    const row = await resolveCropFromV2(id)

    // Validate + normalise any explicit faction the user passed. A typo
    // like "space_marins" or a paste of garbage would otherwise land in
    // labels.csv unvalidated and pollute the training set. An alias
    // (e.g. "blood_angels") auto-resolves to its canonical collapse
    // ("space_marines"). Sentinel / audit paths still skip the lookup —
    // they deliberately don't require a valid faction.
    const isSentinel = effectiveSlug.startsWith('__') && effectiveSlug.endsWith('__')
    const skipFactionLookup = isSentinel || isAudit
    let suppliedFaction = ''
    if (!skipFactionLookup) {
      suppliedFaction = await assertValidFaction(faction)
    }
    // Resolve faction: explicit (validated) > row.faction > unambiguous
    // slug → faction. Keep existing row.faction as a fallback even if it
    // predates validation — don't retroactively reject historical rows.
    let resolvedFaction = (suppliedFaction || row.faction || '').trim()
    if (!resolvedFaction && !skipFactionLookup) {
      const slug2factions = await buildSlugToFactions()
      const s = slug2factions.get(effectiveSlug)
      if (s && s.size === 1) resolvedFaction = [...s][0]
    }
    if (!resolvedFaction && !skipFactionLookup) {
      const err = new Error(
        `Faction is required: slug '${effectiveSlug}' is ambiguous (matches multiple factions). Pass faction in the request body.`
      )
      err.status = 400; throw err
    }

    // Single read → patch every target row in memory → single write.
    // The old loop did N reads and N writes, which (a) was O(N²) on a large
    // CSV, and (b) left the file in an intermediate state after every
    // iteration — a crash mid-loop or a concurrent write would fractionally
    // update the batch. One atomic replacement closes that window.
    const { headers, rows: allRows } = await readLabelsCsv(csvPath)
    const targetPaths = new Set([row.crop_path])
    if (copy_to_siblings && row.instance_id) {
      for (const r of allRows) {
        if (r.instance_id !== row.instance_id) continue
        if (r.crop_path === row.crop_path) continue
        // Don't clobber sibling rows already marked as bad / unknown /
        // ambiguous — those sentinels mean "this crop is broken", which is
        // orthogonal to the label we're propagating here.
        if ((r.unit_slug || '').startsWith('__')) continue
        targetPaths.add(r.crop_path)
      }
    }

    const now = utcNowIso()
    let lastUpdated = null
    const updatedRows = allRows.map((r) => {
      if (!targetPaths.has(r.crop_path)) return r
      // Inherit existing notes. When a previously-audit row gets a real
      // label, strip the flag — otherwise it'd linger forever even though
      // unit_slug would already keep the row out of the audit filter.
      let carried = r.notes || ''
      if (!isAudit && /\bflag:audit\b/.test(carried)) {
        carried = carried
          .split(/\s*;\s*/)
          .filter((p) => p && !/^flag:audit$/.test(p))
          .join('; ')
      }
      let appendedNotes = noteText
        ? (carried ? `${carried} | ${noteText}` : noteText)
        : carried
      // Audit rows carry a notes flag so the UI can filter them into an
      // "audit pile" later, and so the gallery builder can tell an
      // intentionally-blank slug apart from a row it simply hasn't reached.
      if (isAudit && !/\bflag:audit\b/.test(appendedNotes)) {
        appendedNotes = appendedNotes
          ? `${appendedNotes}; ${AUDIT_FLAG}`
          : AUDIT_FLAG
      }
      const merged = {
        ...r,
        faction: resolvedFaction,
        unit_slug: effectiveSlug,
        suggested_by: 'human',
        confidence: '1.0000',
        labeller,
        created_at: now,
        notes: appendedNotes,
      }
      for (const c of V2_COLUMNS) {
        if (!(c in merged)) merged[c] = ''
      }
      if (r.crop_path === row.crop_path) lastUpdated = merged
      return merged
    })
    await writeLabelsCsv(csvPath, updatedRows, { columns: mergeColumns(headers) })

    return {
      id,
      crop_path: row.crop_path,
      unit_slug: lastUpdated?.unit_slug ?? effectiveSlug,
      faction: lastUpdated?.faction ?? resolvedFaction,
      notes: lastUpdated?.notes ?? noteText,
      copied_to: targetPaths.size - 1,  // number of siblings ALSO updated
      status: status || null,
    }
  })
}

/**
 * Redraw bounding boxes on a source scene image.
 *
 * Flow:
 *   1. The original crop (by id) is marked as __bad_crop__ in labels.csv —
 *      the auto-detected region was wrong.
 *   2. For each new bbox the user drew on the SOURCE SCENE image, we crop
 *      a fresh file (with 5% padding, matching scripts/extract_cmon_crops.py)
 *      and append a new label row with suggested_by='human_redraw'. The
 *      faction from the bad crop is carried over (it was usually correct,
 *      just the region was wrong).
 *
 * bboxes: array of {x, y, w, h} in IMAGE-pixel coordinates of the scene.
 *         Caller (the labeller UI) is responsible for converting canvas
 *         display coords → image coords via the scale factor.
 *
 * Returns: { marked_bad: crop_path, created: [...] }
 */
export async function redrawCrops(cropId, bboxes, labeller = 'human') {
  if (!Array.isArray(bboxes) || !bboxes.length) {
    const err = new Error('at least one bbox required')
    err.status = 400; throw err
  }
  const cfg = getLabellingConfig()
  const csvPath = resolveLabellingPath(cfg.labelsCsvV2)

  // Serialise the whole read-extract-write window — another request's save
  // or redraw landing between our readLabelsCsv and writeLabelsCsv would
  // be silently overwritten by our stale-rows snapshot otherwise.
  return withCsvLock(csvPath, async () => {
    const { headers, rows } = await readLabelsCsv(csvPath)

    // Locate the original crop's row (O(N) scan, acceptable at 10K rows).
    const row = rows.find((r) => cropIdFromPath(r.crop_path) === cropId)
    if (!row) { const err = new Error(`unknown crop id: ${cropId}`); err.status = 404; throw err }
    if (row.source !== 'cmon') {
      const err = new Error(`redraw only supported for CMON crops (got source=${row.source})`)
      err.status = 400; throw err
    }

    const viewIdx = row.view_idx === '' ? 0 : parseInt(row.view_idx, 10)
    const scenePath = await resolveSceneImagePath(row.instance_id, viewIdx)
    if (!scenePath) {
      const err = new Error(`source scene image not found for ${row.instance_id} view ${viewIdx}`)
      err.status = 404; throw err
    }

    // Compute where new crop files live (same directory as the original bad crop)
    const repoRoot = resolveLabellingPath(cfg.cropsRepoRoot)
    const originalAbs = resolveCropPathFromCsv(row.crop_path)
    const cropDir = path.dirname(originalAbs)
    await fs.mkdir(cropDir, { recursive: true })

    const extracted = await extractRedrawCrops({
      scenePath, bboxes, cropDir, viewIdx, repoRoot,
      instanceId: row.instance_id, sourceRef: row.source_ref, faction: row.faction || '',
    })

    try {
      const updatedRows = markSiblingsBad(rows, row.instance_id, viewIdx, labeller)
      await writeLabelsCsv(csvPath, [...updatedRows.rows, ...extracted.newRows], {
        columns: mergeColumns(headers),
      })
      try {
        await promoteTempCrops(extracted.tmpPairs)
      } catch (promoteErr) {
        // CSV was written but some JPEGs failed to rename. Roll back the rows
        // that point at missing files so the queue doesn't keep serving 404s.
        if (Array.isArray(promoteErr.failed)) {
          await rollbackFailedPromotions(
            csvPath, headers, updatedRows.rows, extracted.newRows, promoteErr.failed
          )
        }
        throw promoteErr
      }
      return { marked_bad: updatedRows.markedBad, created: extracted.created }
    } catch (err) {
      await cleanupTempCrops(extracted.tmpPairs)
      throw err
    }
  })
}


/**
 * Redraw bounding boxes on a specific (instance, view_idx) — works even
 * when NO existing crops exist for that view (e.g. the detector emitted
 * zero boxes). This is the "multi-view redraw" variant that the UI calls
 * per tab; the per-crop `redrawCrops` above is a legacy shortcut for the
 * single-view case.
 */
export async function redrawSceneView(instanceId, viewIdx, bboxes, labeller = 'human', opts = {}) {
  const { replaceCropId } = opts
  if (!instanceId || !instanceId.startsWith('cmon:')) {
    throw Object.assign(new Error('only cmon instances supported'), { status: 400 })
  }
  if (!Array.isArray(bboxes) || !bboxes.length) {
    throw Object.assign(new Error('at least one bbox required'), { status: 400 })
  }
  viewIdx = Number(viewIdx)
  if (!Number.isInteger(viewIdx) || viewIdx < 0) {
    throw Object.assign(new Error('view_idx must be a non-negative integer'), { status: 400 })
  }

  const scenePath = await resolveSceneImagePath(instanceId, viewIdx)
  if (!scenePath) {
    throw Object.assign(new Error(`no scene image for ${instanceId} view ${viewIdx}`), { status: 404 })
  }

  const cfg = getLabellingConfig()
  const csvPath = resolveLabellingPath(cfg.labelsCsvV2)

  return withCsvLock(csvPath, async () => {
    const { headers, rows } = await readLabelsCsv(csvPath)

    // Existing rows for this (instance, view) — may be zero when the detector
    // missed the whole photo. Used for faction inheritance + mark-bad pass.
    const viewRows = rows.filter((r) => {
      if (r.instance_id !== instanceId) return false
      const rv = r.view_idx === '' ? 0 : parseInt(r.view_idx, 10)
      return rv === viewIdx
    })
    const sourceFaction = viewRows.find((r) => r.faction)?.faction || ''
    const sourceRef = viewRows[0]?.source_ref || instanceId

    // Crop directory is keyed on the CMON entry_id (the part after "cmon:").
    // Create it if this is the first crop ever for this entry.
    const entryId = instanceId.slice('cmon:'.length)
    assertValidEntryId(entryId)
    const repoRoot = resolveLabellingPath(cfg.cropsRepoRoot)
    const cropDir = path.resolve(repoRoot, 'data', 'crops', 'cmon', entryId)
    assertInsideRoot(cropDir, repoRoot)
    await fs.mkdir(cropDir, { recursive: true })

    const extracted = await extractRedrawCrops({
      scenePath, bboxes, cropDir, viewIdx, repoRoot,
      instanceId, sourceRef, faction: sourceFaction,
    })

    try {
      // When the user opened the redraw modal on a specific crop, force-mark
      // THAT crop as bad even if it's a prior `human_redraw` row — otherwise
      // each iterative "nudge the box a bit" creates a new file and leaves
      // the old redraw in the queue, producing visual duplicates.
      const forcePathsBad = new Set()
      if (replaceCropId) {
        const target = rows.find((r) => cropIdFromPath(r.crop_path) === replaceCropId)
        if (target) forcePathsBad.add(target.crop_path)
      }
      const updatedRows = markSiblingsBad(rows, instanceId, viewIdx, labeller, forcePathsBad)
      await writeLabelsCsv(csvPath, [...updatedRows.rows, ...extracted.newRows], {
        columns: mergeColumns(headers),
      })
      try {
        await promoteTempCrops(extracted.tmpPairs)
      } catch (promoteErr) {
        if (Array.isArray(promoteErr.failed)) {
          await rollbackFailedPromotions(
            csvPath, headers, updatedRows.rows, extracted.newRows, promoteErr.failed
          )
        }
        throw promoteErr
      }
      return {
        instance_id: instanceId,
        view_idx: viewIdx,
        marked_bad: updatedRows.markedBad,
        created: extracted.created,
      }
    } catch (err) {
      await cleanupTempCrops(extracted.tmpPairs)
      throw err
    }
  })
}

/**
 * Edit the bbox of a single crop in-place. Re-extracts one fresh JPEG from
 * the scene at the new coords (with the same 5%-of-longer-side padding that
 * the Python extractor uses), swaps it atomically over the existing file,
 * and updates the row's `notes` with `bbox=x0,y0,w,h`. Sibling crops on the
 * same view are NOT touched — use this when you want to nudge one box, not
 * start the whole view over.
 *
 * Optional label fields let the UI combine "move the box" and "confirm the
 * label" in one operation:
 *   - opts.unit_slug : if non-empty, saves the row as human-confirmed
 *     (suggested_by='human', confidence=1.0, clears flag:audit).
 *   - opts.faction   : overrides the row's faction (or used as the
 *     inferred one when the slug is unambiguous).
 *   - opts.status='audit' : flag the row as deferred (blank slug,
 *     faction preserved, flag:audit added to notes). Mutually exclusive
 *     with unit_slug.
 *   - opts.labeller  : who made the edit (required for auditability).
 *
 * If NEITHER unit_slug nor status is passed, the row's existing
 * faction/slug/suggested_by are preserved — bbox-only edit mode, for when
 * the user wants to fix the geometry now and come back to labelling later.
 *
 * Ordering guarantee: new JPEG → CSV write → atomic rename. A rename
 * failure after the CSV commit triggers a best-effort CSV rollback so the
 * queue never points at a file we failed to swap.
 */
export async function editCropBbox(cropId, bbox, opts = {}) {
  const { faction, unit_slug, status, labeller = 'human' } = opts
  if (!bbox || typeof bbox !== 'object') {
    throw Object.assign(new Error('bbox required'), { status: 400 })
  }
  const x = Number(bbox.x), y = Number(bbox.y)
  const w = Number(bbox.w), h = Number(bbox.h)
  if (![x, y, w, h].every(Number.isFinite)) {
    throw Object.assign(new Error('bbox.x/y/w/h must all be finite numbers'), { status: 400 })
  }
  if (w <= 0 || h <= 0) {
    throw Object.assign(new Error('bbox must have positive w and h'), { status: 400 })
  }
  if (status && status !== 'audit') {
    throw Object.assign(new Error(`status must be 'audit' or omitted`), { status: 400 })
  }
  // Validate + normalise an explicit faction up-front (before touching the
  // CSV lock). Same reasoning as saveLabel: reject typos, auto-canonicalise
  // aliases. Empty faction is fine — preserves existing row.faction.
  const validatedFaction = await assertValidFaction(faction)

  const cfg = getLabellingConfig()
  const csvPath = resolveLabellingPath(cfg.labelsCsvV2)

  return withCsvLock(csvPath, async () => {
    const { headers, rows } = await readLabelsCsv(csvPath)
    const row = rows.find((r) => cropIdFromPath(r.crop_path) === cropId)
    if (!row) {
      throw Object.assign(new Error(`unknown crop id: ${cropId}`), { status: 404 })
    }
    if (row.source !== 'cmon') {
      throw Object.assign(
        new Error(`edit only supported for CMON crops (got source=${row.source})`),
        { status: 400 }
      )
    }

    const viewIdx = row.view_idx === '' ? 0 : parseInt(row.view_idx, 10)
    const scenePath = await resolveSceneImagePath(row.instance_id, viewIdx)
    if (!scenePath) {
      throw Object.assign(
        new Error(`no scene image for ${row.instance_id} view ${viewIdx}`),
        { status: 404 }
      )
    }

    const meta = await sharp(scenePath).metadata()
    const imgW = meta.width, imgH = meta.height
    const pad = Math.max(w, h) * 0.05
    const x0 = Math.max(0, Math.round(x - pad))
    const y0 = Math.max(0, Math.round(y - pad))
    const x1 = Math.min(imgW, Math.round(x + w + pad))
    const y1 = Math.min(imgH, Math.round(y + h + pad))
    const cropW = x1 - x0, cropH = y1 - y0
    if (cropW <= 0 || cropH <= 0) {
      throw Object.assign(
        new Error('bbox produces a zero-area crop after padding + image-bound clamp'),
        { status: 400 }
      )
    }

    const finalAbs = resolveCropPathFromCsv(row.crop_path)
    const tmpAbs = finalAbs + '.editing'
    await sharp(scenePath)
      .extract({ left: x0, top: y0, width: cropW, height: cropH })
      .jpeg({ quality: 92 })
      .toFile(tmpAbs)

    // Build the patched row. Notes: strip any existing bbox= / scene= /
    // edited_at= tags and rebuild with the fresh ones — segments are
    // separated by ';'. Everything else (title, artist, detector_conf,
    // flag:audit if we don't touch it, etc.) is preserved.
    const priorNotes = String(row.notes || '')
      .split(/\s*;\s*/)
      .filter((p) => p && !/^bbox=/.test(p) && !/^scene=/.test(p) && !/^edited_at=/.test(p))
    const bboxTag = `bbox=${x0},${y0},${cropW},${cropH}`
    const sceneTag = `scene=${row.instance_id}:${viewIdx}`
    const editedTag = `edited_at=${utcNowIso()}`
    const now = utcNowIso()

    const updatedRow = {
      ...row,
      labeller,
      created_at: now,
    }

    const slugClean = typeof unit_slug === 'string' ? unit_slug.trim().toLowerCase() : ''

    if (slugClean) {
      // Full save: bbox + confirmed label in one step.
      updatedRow.unit_slug = slugClean
      updatedRow.suggested_by = 'human'
      updatedRow.confidence = '1.0000'
      // Use the already-validated faction; fall back to the row's existing
      // value (unchanged — historical rows don't need re-validation).
      let fac = (validatedFaction || row.faction || '').trim()
      if (!fac) {
        const slug2 = await buildSlugToFactions()
        const s = slug2.get(slugClean)
        if (s && s.size === 1) fac = [...s][0]
      }
      if (!fac) {
        // Clean up the tmp file since we're throwing before commit.
        try { await fs.unlink(tmpAbs) } catch {}
        throw Object.assign(
          new Error(`faction required: slug '${slugClean}' matches multiple factions — pass faction in the body`),
          { status: 400 }
        )
      }
      updatedRow.faction = fac
      updatedRow.notes = [...priorNotes.filter((p) => p !== 'flag:audit'), bboxTag, sceneTag, editedTag].join('; ')
    } else if (status === 'audit') {
      // Bbox + defer: clear slug, keep/set faction, flag as audit.
      updatedRow.unit_slug = ''
      updatedRow.faction = (validatedFaction || row.faction || '').trim()
      updatedRow.suggested_by = 'human'
      updatedRow.confidence = '1.0000'
      const notesWithoutAudit = priorNotes.filter((p) => p !== 'flag:audit')
      updatedRow.notes = [...notesWithoutAudit, bboxTag, sceneTag, editedTag, 'flag:audit'].join('; ')
    } else {
      // Bbox-only edit: preserve existing faction/slug/suggested_by.
      if (validatedFaction) updatedRow.faction = validatedFaction
      updatedRow.notes = [...priorNotes, bboxTag, sceneTag, editedTag].join('; ')
    }

    for (const c of V2_COLUMNS) {
      if (!(c in updatedRow)) updatedRow[c] = ''
    }

    const newRows = rows.map((r) => r.crop_path === row.crop_path ? updatedRow : r)

    // CSV first, so a rename failure can roll it back cleanly.
    try {
      await writeLabelsCsv(csvPath, newRows, { columns: mergeColumns(headers) })
    } catch (err) {
      try { await fs.unlink(tmpAbs) } catch {}
      throw err
    }

    try {
      await fs.rename(tmpAbs, finalAbs)
    } catch (renameErr) {
      logger.error(`edit rename ${tmpAbs} → ${finalAbs} failed: ${renameErr.message}`)
      // Roll the CSV back to the pre-edit row so on-disk state matches.
      try {
        await writeLabelsCsv(
          csvPath,
          rows.map((r) => r.crop_path === row.crop_path ? row : r),
          { columns: mergeColumns(headers) }
        )
      } catch (rbErr) {
        logger.error(`edit CSV rollback also failed: ${rbErr.message}`)
      }
      try { await fs.unlink(tmpAbs) } catch {}
      throw Object.assign(
        new Error(`failed to commit edited JPEG: ${renameErr.message}`),
        { status: 500 }
      )
    }

    return {
      id: cropId,
      crop_path: row.crop_path,
      bbox: { x: x0, y: y0, w: cropW, h: cropH },
      unit_slug: updatedRow.unit_slug,
      faction: updatedRow.faction,
      notes: updatedRow.notes,
      status: slugClean ? 'confirmed' : (status === 'audit' ? 'audit' : 'bbox_only'),
    }
  })
}

// ── Shared redraw helpers ──────────────────────────────────────────────────
// Both redrawCrops and redrawSceneView follow the same pattern: write JPEGs
// to disk, rewrite the CSV, mark existing siblings in the view as bad. The
// helpers below share that work so the two entry points stay thin, and so
// the atomicity contract (JPEGs only committed after a successful CSV write)
// lives in one place.

/** Walk bboxes, validate, and write each resulting JPEG to a `.tmp` path.
 *  Returns the list of (tmp, final) pairs so the caller can rename-commit
 *  after the CSV write succeeds, plus the new row objects + created records.
 *  On bbox-level validation failure, already-written temps are cleaned up
 *  before rethrowing. */
async function extractRedrawCrops({
  scenePath, bboxes, cropDir, viewIdx, repoRoot, instanceId, sourceRef, faction,
}) {
  const meta = await sharp(scenePath).metadata()
  const imgW = meta.width, imgH = meta.height

  const viewPrefix = `${String(viewIdx).padStart(2, '0')}_r`
  let nextNum = 1
  try {
    const existing = await fs.readdir(cropDir)
    const used = existing
      .filter((f) => f.startsWith(viewPrefix) && f.endsWith('.jpg'))
      .map((f) => parseInt(f.slice(viewPrefix.length, -4), 10))
      .filter((n) => !isNaN(n))
    if (used.length) nextNum = Math.max(...used) + 1
  } catch {}

  const newRows = []
  const created = []
  const tmpPairs = []

  try {
    for (const bbox of bboxes) {
      const x = Number(bbox.x), y = Number(bbox.y)
      const w = Number(bbox.w), h = Number(bbox.h)
      if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(w) || !Number.isFinite(h)) {
        throw Object.assign(new Error(`invalid bbox ${JSON.stringify(bbox)}`), { status: 400 })
      }
      if (w <= 0 || h <= 0) {
        throw Object.assign(new Error(`bbox must have positive w/h: ${JSON.stringify(bbox)}`), { status: 400 })
      }

      // 5% padding on the longer side (matches Python extract_cmon_crops)
      const pad = Math.max(w, h) * 0.05
      const x0 = Math.max(0, Math.round(x - pad))
      const y0 = Math.max(0, Math.round(y - pad))
      const x1 = Math.min(imgW, Math.round(x + w + pad))
      const y1 = Math.min(imgH, Math.round(y + h + pad))
      const cropW = x1 - x0, cropH = y1 - y0
      if (cropW <= 0 || cropH <= 0) continue

      const filename = `${String(viewIdx).padStart(2, '0')}_r${String(nextNum).padStart(2, '0')}.jpg`
      const finalAbs = path.join(cropDir, filename)
      const tmpAbs = finalAbs + '.tmp'
      await sharp(scenePath)
        .extract({ left: x0, top: y0, width: cropW, height: cropH })
        .jpeg({ quality: 92 })
        .toFile(tmpAbs)
      tmpPairs.push({ tmp: tmpAbs, final: finalAbs })

      const relOut = path.relative(repoRoot, finalAbs).split(path.sep).join('/')
      newRows.push({
        crop_path: relOut,
        source: 'cmon',
        source_ref: sourceRef,
        instance_id: instanceId,
        view_idx: String(viewIdx),
        faction,
        unit_slug: '',
        suggested_by: 'human_redraw',
        confidence: '',
        labeller: '',
        split: '',
        created_at: utcNowIso(),
        notes: `human_redraw=${nextNum}; bbox=${x0},${y0},${cropW},${cropH}; scene=${instanceId}:${viewIdx}`,
      })
      created.push({ crop_path: relOut, filename })
      nextNum++
    }
  } catch (err) {
    await cleanupTempCrops(tmpPairs)
    throw err
  }

  return { tmpPairs, newRows, created }
}

/** Produce a fresh rows array with every non-bad, non-redraw row in
 *  (instanceId, viewIdx) flipped to `__bad_crop__`. Returns the new array +
 *  list of crop_paths that were changed. Does NOT mutate the input (which
 *  matters because readLabelsCsv now returns cached references). */
function markSiblingsBad(rows, instanceId, viewIdx, labeller, forcePathsBad = new Set()) {
  const markedBad = []
  const now = utcNowIso()
  const updated = rows.map((r) => {
    if (r.instance_id !== instanceId) return r
    const rView = r.view_idx === '' ? 0 : parseInt(r.view_idx, 10)
    if (rView !== viewIdx) return r
    if (r.unit_slug === '__bad_crop__') return r
    // Confirmed human_redraw rows (already given a real label) are preserved
    // — a user's deliberate, labelled box shouldn't be trampled by a later
    // redraw on the same view. Unconfirmed redraws, however, are just stale
    // iterations of the current "nudge the box" flow; marking them bad here
    // stops iterative redraws from accumulating ghost rows in the queue.
    // A caller can still force-mark any row via `forcePathsBad` (used when
    // the modal was opened directly ON a specific redraw).
    const forced = forcePathsBad.has(r.crop_path)
    const isHumanRedraw = (r.suggested_by || '').startsWith('human_redraw')
    const slug = (r.unit_slug || '').trim()
    const isConfirmedRedraw = isHumanRedraw && !!slug && !slug.startsWith('__')
    if (!forced && isConfirmedRedraw) return r
    const en = r.notes || ''
    markedBad.push(r.crop_path)
    return {
      ...r,
      unit_slug: '__bad_crop__',
      suggested_by: 'human',
      confidence: '1.0000',
      labeller,
      created_at: now,
      notes: en + (en ? '; ' : '') + `redrawn_view=${viewIdx}`,
    }
  })
  return { rows: updated, markedBad }
}

/** Rename every temp JPEG to its final path. Called after the CSV write
 *  succeeds. On any failure, throws a structured error so the caller can
 *  roll back the CSV rows whose files didn't land — otherwise the queue
 *  would show broken-image crops forever. Best-effort: already-renamed
 *  pairs stay on disk (they're valid files with matching CSV rows); only
 *  the failed rows need rollback. */
async function promoteTempCrops(pairs) {
  const promoted = []
  const failed = []
  for (const pair of pairs) {
    try {
      await fs.rename(pair.tmp, pair.final)
      promoted.push(pair)
    } catch (err) {
      logger.error(`failed to promote ${pair.tmp} → ${pair.final}: ${err.message}`)
      failed.push({ ...pair, cause: err.message })
    }
  }
  if (failed.length) {
    const err = new Error(
      `promoted ${promoted.length}/${pairs.length} redraw crops; ${failed.length} failed to rename`
    )
    err.status = 500
    err.promoted = promoted
    err.failed = failed
    throw err
  }
}

/** Best-effort rollback after promoteTempCrops partially fails. Rewrites
 *  the CSV without the rows that point at files that never landed on disk.
 *  Logs and swallows any secondary failure so the caller's original error
 *  (from promote) is what ultimately propagates to the client. */
async function rollbackFailedPromotions(csvPath, headers, baseRows, newRows, failedPairs) {
  const cfg = getLabellingConfig()
  const repoRoot = resolveLabellingPath(cfg.cropsRepoRoot)
  const failedRelPaths = new Set(
    failedPairs.map((p) => path.relative(repoRoot, p.final).split(path.sep).join('/'))
  )
  const kept = newRows.filter((r) => !failedRelPaths.has(r.crop_path))
  try {
    await writeLabelsCsv(csvPath, [...baseRows, ...kept], { columns: mergeColumns(headers) })
  } catch (err) {
    logger.error(`CSV rollback after promote failure also failed: ${err.message}`)
  }
}

/** Unlink every temp JPEG. Called when the CSV write failed; the committed
 *  truth is whatever was on disk before we started, so the JPEGs we wrote
 *  are garbage. */
async function cleanupTempCrops(pairs) {
  for (const { tmp } of pairs) {
    try { await fs.unlink(tmp) } catch {}
  }
}

/** Health check. v2-only — v1 fallback was retired in the 2026-04 audit sweep. */
export async function selfCheck() {
  const cfg = getLabellingConfig()
  if (!cfg.enabled) return { enabled: false }
  const labelsCsvV2 = resolveLabellingPath(cfg.labelsCsvV2)
  try {
    await fs.access(labelsCsvV2)
    return {
      enabled: true,
      healthy: true,
      mode: 'v2',
      labelsCsvV2,
      cmonRoot: resolveLabellingPath(cfg.cmonRoot),
    }
  } catch {
    return {
      enabled: true,
      healthy: false,
      reason: `labels.csv not found at ${labelsCsvV2}`,
    }
  }
}

// V2 export helper — useful for the `/api/labelling/factions` endpoint
export { V2_COLUMNS }
