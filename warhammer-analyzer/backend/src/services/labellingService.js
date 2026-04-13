/**
 * Labelling Service
 *
 * Repurposes the analyzer into an AI-assisted labelling tool for the
 * Phase 1 retrieval prototype (see ../../../STRATEGY.md). Reads the
 * crops already on disk at scripts/phase1/crops/, suggests a unit slug
 * per crop via the configured LLM, and persists confirmed labels back
 * to scripts/phase1/labels.csv atomically.
 *
 * All IO is scoped to the configured cropsDir / labelsCsv / cheatsheet
 * paths — no arbitrary-path access.
 */

import fs from 'node:fs/promises'
import path from 'node:path'
import { createHash } from 'node:crypto'
import { getLabellingConfig, createProvider } from '../config/pipeline.js'
import { logger } from '../utils/logger.js'

let _cheatsheetByFaction = null

function resolveLabellingPath(configPath) {
  // Paths in config are relative to the warhammer-analyzer root.
  return path.resolve(process.cwd(), configPath)
}

/**
 * Parse the unit_slugs_cheatsheet.md once at startup. Returns a Map
 * keyed by faction slug, value = array of allowed unit slugs.
 */
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
    // Lines look like: `- `plague_marines` — Plague Marines`
    const slugMatch = line.match(/^\s*-\s*`([a-z0-9_]+)`/i)
    if (slugMatch && currentFaction) {
      map.get(currentFaction).push(slugMatch[1])
    }
  }
  _cheatsheetByFaction = map
  return map
}

/**
 * Build a stable crop ID from its path relative to the crops dir. Simple
 * MD5 of the relative path — stable across runs, filesystem-safe.
 */
function cropIdFromRelPath(relPath) {
  return createHash('md5').update(relPath).digest('hex').slice(0, 12)
}

/**
 * Walk the crops directory and return all image files grouped by faction.
 * Structure on disk: cropsDir/{faction}/{filename}.jpg
 */
async function walkCrops() {
  const cfg = getLabellingConfig()
  const cropsDir = resolveLabellingPath(cfg.cropsDir)

  const factions = await fs.readdir(cropsDir, { withFileTypes: true }).catch((err) => {
    if (err.code === 'ENOENT') return []
    throw err
  })

  const crops = []
  for (const facEntry of factions) {
    if (!facEntry.isDirectory()) continue
    const faction = facEntry.name
    const facDir = path.join(cropsDir, faction)
    const files = await fs.readdir(facDir).catch(() => [])
    for (const file of files.sort()) {
      if (!/\.(jpe?g|png|webp)$/i.test(file)) continue
      const abs = path.join(facDir, file)
      const rel = path.relative(cropsDir, abs) // faction/file
      crops.push({
        id: cropIdFromRelPath(rel),
        faction,
        filename: file,
        relPath: rel,
        absPath: abs,
      })
    }
  }
  return crops
}

/**
 * Read the current labels.csv. Returns a Map<crop_path, row> where
 * crop_path is the value from the CSV exactly (the labels.csv stores
 * repo-relative paths like "scripts/phase1/crops/..../x.jpg").
 */
async function readLabelsCsv() {
  const cfg = getLabellingConfig()
  const csvPath = resolveLabellingPath(cfg.labelsCsv)
  let text
  try {
    text = await fs.readFile(csvPath, 'utf8')
  } catch (err) {
    if (err.code === 'ENOENT') return { headers: ['crop_path', 'faction', 'unit_slug', 'notes'], byPath: new Map() }
    throw err
  }

  const lines = text.split('\n').filter((l) => l.length > 0)
  if (lines.length === 0) {
    return { headers: ['crop_path', 'faction', 'unit_slug', 'notes'], byPath: new Map() }
  }
  const headers = lines[0].split(',')
  const byPath = new Map()
  for (const line of lines.slice(1)) {
    const cells = splitCsvLine(line)
    const row = Object.fromEntries(headers.map((h, i) => [h.trim(), (cells[i] ?? '').trim()]))
    if (row.crop_path) byPath.set(row.crop_path, row)
  }
  return { headers, byPath }
}

/**
 * Minimal CSV line splitter — handles the "simple" case we actually write
 * (no embedded commas, no quoted cells). If someone manually edits the
 * CSV with a comma inside notes, this will break; in that case tell them
 * to fix the source CSV.
 */
function splitCsvLine(line) {
  return line.split(',').map((s) => s.trim())
}

/**
 * Write labels.csv atomically (tmp + rename). Preserves the original
 * header order, even if the labels.csv has extra columns beyond our own.
 */
async function writeLabelsCsv({ headers, byPath }) {
  const cfg = getLabellingConfig()
  const csvPath = resolveLabellingPath(cfg.labelsCsv)
  const lines = [headers.join(',')]
  // Sort rows by crop_path for stable diffs.
  const sorted = [...byPath.values()].sort((a, b) => a.crop_path.localeCompare(b.crop_path))
  for (const row of sorted) {
    const cells = headers.map((h) => (row[h.trim()] ?? '').replace(/,/g, ';').replace(/\n/g, ' '))
    lines.push(cells.join(','))
  }
  const tmp = csvPath + '.tmp'
  await fs.writeFile(tmp, lines.join('\n') + '\n', 'utf8')
  await fs.rename(tmp, csvPath)
}

/**
 * Derive the label_key (CSV `crop_path` value) for a crop. We re-derive
 * from the configured cropsDir rather than hardcoding `scripts/phase1/`,
 * so pointing LABELLING_CROPS_DIR at a different path (e.g. Phase 2)
 * produces matching CSV keys. Result is a repo-relative POSIX path.
 */
function labelKeyForCrop(crop) {
  const cfg = getLabellingConfig()
  const absCropsDir = resolveLabellingPath(cfg.cropsDir)
  const repoRoot = path.resolve(process.cwd(), '..')
  const absCropPath = path.join(absCropsDir, crop.relPath)
  const relFromRepo = path.relative(repoRoot, absCropPath)
  return relFromRepo.split(path.sep).join('/')
}

/**
 * List all crops with their labelling status. Cross-references the
 * crops on disk with labels.csv.
 *
 * Returns:
 *   [
 *     { id, faction, filename, relPath, labelled, unit_slug, notes, label_key },
 *     ...
 *   ]
 * label_key is the CSV "crop_path" value (repo-relative).
 */
export async function listCrops() {
  const [crops, labels] = await Promise.all([walkCrops(), readLabelsCsv()])
  return crops.map((c) => {
    const labelKey = labelKeyForCrop(c)
    const row = labels.byPath.get(labelKey)
    return {
      id: c.id,
      faction: c.faction,
      filename: c.filename,
      relPath: c.relPath,
      absPath: c.absPath,
      labelKey,
      labelled: !!(row && row.unit_slug),
      unit_slug: row?.unit_slug ?? null,
      notes: row?.notes ?? '',
    }
  })
}

/**
 * Return the absolute path to a crop given its id. Rejects if the id
 * doesn't resolve to a known crop (guards against path traversal).
 */
export async function resolveCropPath(id) {
  const crops = await walkCrops()
  const match = crops.find((c) => c.id === id)
  if (!match) {
    const err = new Error(`Unknown crop id: ${id}`)
    err.status = 404
    throw err
  }
  return match
}

/**
 * Suggest a unit slug for a crop. Returns the top suggestion plus up
 * to 4 alternatives so the UI can show a "top-5 pills" interface.
 *
 * Uses the configured labelling.suggestProvider / suggestModel.
 */
export async function suggestForCrop(id, { extraAlternatives = 4 } = {}) {
  const crop = await resolveCropPath(id)
  const cheatsheet = await loadCheatsheet()
  const cfg = getLabellingConfig()

  const allowedUnits = cheatsheet.get(crop.faction) || []
  const cheatsheetText = allowedUnits.length
    ? `For ${crop.faction}, valid slugs include: ${allowedUnits.slice(0, 30).join(', ')}${
        allowedUnits.length > 30 ? ', …' : ''
      }.`
    : undefined

  const provider = await createProvider(cfg.suggestProvider, cfg.suggestModel)
  const buffer = await fs.readFile(crop.absPath)

  const t0 = Date.now()
  const primary = await provider.classifyImage(buffer, {
    factionHint: crop.faction,
    allowedUnits,
    cheatsheet: cheatsheetText,
  })
  const elapsedMs = Date.now() - t0

  // Alternatives: ask the LLM for the next-best candidates in the same call
  // would be ideal, but the base prompt returns one pick. For now, offer
  // the allowed list sans the top pick as fallback options in the UI.
  const alternatives = allowedUnits
    .filter((u) => u !== primary.unit)
    .slice(0, extraAlternatives)
    .map((unit) => ({ unit, faction: crop.faction, confidence: null, source: 'cheatsheet' }))

  return {
    crop: { id, faction: crop.faction, filename: crop.filename },
    top: {
      unit: primary.unit,
      faction: primary.faction || crop.faction,
      confidence: primary.confidence,
      reasoning: primary.reasoning,
      source: 'llm',
    },
    alternatives,
    provider: { name: cfg.suggestProvider, model: cfg.suggestModel },
    elapsedMs,
  }
}

/**
 * Save a label for a crop. Writes the row into labels.csv, preserving
 * any other rows (seeded but unlabelled, or labelled by another run).
 */
export async function saveLabel(id, { unit_slug, notes = '' }) {
  if (typeof unit_slug !== 'string' || !unit_slug.trim()) {
    const err = new Error('unit_slug is required')
    err.status = 400
    throw err
  }
  const slug = unit_slug.trim().toLowerCase()
  const noteText = String(notes || '').trim()
  const crop = await resolveCropPath(id)
  const labels = await readLabelsCsv()

  const labelKey = labelKeyForCrop(crop)
  const existing = labels.byPath.get(labelKey) || {}
  const row = {
    ...existing,
    crop_path: labelKey,
    faction: crop.faction,
    unit_slug: slug,
    notes: noteText,
  }
  // Fill in any split column that auto_split.py may have populated,
  // preserving it across saves.
  if (existing.split) row.split = existing.split
  labels.byPath.set(labelKey, row)

  // Ensure required columns exist in the header. Compare trimmed so we
  // don't duplicate a column because of whitespace in the on-disk CSV.
  const required = ['crop_path', 'faction', 'unit_slug', 'notes']
  const existingHeaders = labels.headers.map((h) => h.trim())
  for (const h of required) {
    if (!existingHeaders.includes(h)) {
      labels.headers.push(h)
      existingHeaders.push(h)
    }
  }

  await writeLabelsCsv(labels)
  return { id, unit_slug: slug, notes: noteText }
}

/**
 * Sanity check at startup: cropsDir and labels.csv must be resolvable.
 * Non-fatal — logs a warning if the labelling mode can't be used.
 */
export async function selfCheck() {
  const cfg = getLabellingConfig()
  if (!cfg.enabled) return { enabled: false }
  const cropsDir = resolveLabellingPath(cfg.cropsDir)
  const labelsCsv = resolveLabellingPath(cfg.labelsCsv)
  try {
    await fs.access(cropsDir)
  } catch {
    logger.warn(`Labelling mode enabled but cropsDir missing: ${cropsDir}`)
    return { enabled: true, healthy: false, reason: 'crops_dir_missing', cropsDir }
  }
  try {
    await fs.access(labelsCsv)
  } catch {
    logger.warn(`Labelling mode enabled but labels.csv missing: ${labelsCsv} (will be created on first save)`)
  }
  return { enabled: true, healthy: true, cropsDir, labelsCsv }
}
