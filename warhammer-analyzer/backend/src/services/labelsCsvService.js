/**
 * labels.csv v2 read/write helper.
 *
 * Mirrors the Python `photoanalyzer.label.schema` module (v2 schema, 13 columns)
 * so the labelling UI can read/append rows without a separate Python hop.
 *
 * Why roll our own CSV parser instead of pulling a dep:
 *  - warhammer-analyzer/backend has zero CSV libs today and I don't want to
 *    add one for 80 lines of well-specified RFC-4180-ish parsing.
 *  - We only ever read/write our own files — no wildcards, no exotic dialects.
 *  - Full Jest/Node test coverage on the parser below documents the invariants.
 *
 * v2 columns, in order:
 *   crop_path, source, source_ref, instance_id, view_idx, faction, unit_slug,
 *   suggested_by, confidence, labeller, split, created_at, notes
 */

import fs from 'node:fs/promises'
import path from 'node:path'
import lockfile from 'proper-lockfile'

export const V2_COLUMNS = Object.freeze([
  'crop_path',
  'source',
  'source_ref',
  'instance_id',
  'view_idx',
  'faction',
  'unit_slug',
  'suggested_by',
  'confidence',
  'labeller',
  'split',
  'created_at',
  'notes',
])

export const VALID_SOURCES = Object.freeze(new Set([
  'gw_shop', 'cmon', 'dakka', 'reddit', 'wh_community',
  'annotation', 'synthetic', 'user_photo',
]))

// ── CSV parse / serialise ──────────────────────────────────────────────────
/**
 * RFC-4180-ish line parser. Handles:
 *  - unquoted fields with no special chars
 *  - double-quoted fields with embedded commas, newlines, or `""` escapes
 * Returns an array of string cells.
 */
export function parseCsvRow(source, startPos = 0) {
  const cells = []
  let i = startPos
  let cell = ''
  let inQuotes = false
  let lineDone = false

  while (i < source.length && !lineDone) {
    const c = source[i]
    if (inQuotes) {
      if (c === '"') {
        if (source[i + 1] === '"') { cell += '"'; i += 2; continue }
        inQuotes = false
        i += 1
        continue
      }
      cell += c
      i += 1
      continue
    }
    // not in quotes
    if (c === '"' && cell.length === 0) {
      inQuotes = true
      i += 1
      continue
    }
    if (c === ',') {
      cells.push(cell)
      cell = ''
      i += 1
      continue
    }
    if (c === '\r') { i += 1; continue }
    if (c === '\n') { lineDone = true; i += 1; continue }
    cell += c
    i += 1
  }
  if (cell.length > 0 || cells.length > 0) cells.push(cell)
  return { cells, nextPos: i, eof: i >= source.length && !lineDone }
}

/** Prepend `'` to cells whose first char is a spreadsheet formula trigger.
 *  Excel / LibreOffice / Google Sheets evaluate `=`, `+`, `-`, `@`, TAB, and
 *  CR-prefixed values as formulas, which is a live XSS-style hazard if the
 *  CSV is ever opened in a sheet app. Prefixing with `'` neutralises the
 *  formula while preserving readable round-trip in text/diff tools.
 */
export function sanitiseForCsv(s) {
  if (typeof s !== 'string' || s.length === 0) return s
  if (/^[=+\-@\t\r]/.test(s)) return "'" + s
  return s
}

/** Quote a cell if it contains any of: `,`, `"`, `\n`, `\r`. Empty string → `""`
 * style we prefer is: only quote when necessary (matches Python csv.DictWriter
 * defaults). Formula-prefixed values are defanged via `sanitiseForCsv`. */
export function serialiseCell(value) {
  if (value === null || value === undefined) return ''
  const raw = String(value)
  if (raw.length === 0) return ''
  const s = sanitiseForCsv(raw)
  if (/[",\n\r]/.test(s)) {
    return '"' + s.replace(/"/g, '""') + '"'
  }
  return s
}

export function serialiseRow(rowObj, columns = V2_COLUMNS) {
  return columns.map((c) => serialiseCell(rowObj[c])).join(',')
}

/**
 * Parse a full CSV document. Returns { headers, rows } where each row is a
 * plain object keyed by column name.
 */
export function parseCsv(text) {
  if (!text || text.length === 0) return { headers: [], rows: [] }
  let pos = 0
  const { cells: headers, nextPos } = parseCsvRow(text, 0)
  pos = nextPos
  const rows = []
  while (pos < text.length) {
    const { cells, nextPos: np, eof } = parseCsvRow(text, pos)
    pos = np
    if (cells.length === 0 || (cells.length === 1 && cells[0] === '')) {
      if (eof) break
      continue
    }
    const row = {}
    for (let i = 0; i < headers.length; i++) {
      row[headers[i]] = cells[i] ?? ''
    }
    rows.push(row)
    if (eof) break
  }
  return { headers, rows }
}

// ── LabelRecord shape (convenience; JS is duck-typed) ──────────────────────
/**
 * Shape of a v2 row object. All fields are strings as stored in CSV; callers
 * parse view_idx / confidence as numbers when needed.
 *
 * @typedef {Object} LabelRow
 * @property {string} crop_path
 * @property {string} source
 * @property {string} source_ref
 * @property {string} instance_id
 * @property {string} view_idx      (int as string, or empty)
 * @property {string} faction
 * @property {string} unit_slug
 * @property {string} suggested_by
 * @property {string} confidence    (float 0-1 as string, or empty)
 * @property {string} labeller
 * @property {string} split
 * @property {string} created_at
 * @property {string} notes
 */

// ── Per-file async mutex (in-process + cross-process) ────────────────────
// Two layers:
//   1. An in-process Promise chain (`_csvLocks` Map) serialises concurrent
//      callers WITHIN this Node process so they don't race each other.
//   2. A `proper-lockfile` file lock on `<csvPath>.lock` serialises
//      against OTHER processes — Python writers (apply_weak_sup.py,
//      extract_cmon_crops.py, sync_from_canonical.py, etc.) which hold
//      the same-named sidecar lock via the `filelock` library. Both
//      sides respect the same path, so either side blocks the other.
//
// Usage:
//   return withCsvLock(csvPath, async () => {
//     const { headers, rows } = await readLabelsCsv(csvPath)
//     // ...mutate
//     await writeLabelsCsv(csvPath, updated, { columns: mergeColumns(headers) })
//   })
const _csvLocks = new Map()  // csvPath → tail-of-chain Promise

// proper-lockfile insists the target exists before acquiring, so we create
// the CSV file with an empty header line if it's missing. Keeps the lock
// contract simple: one sidecar .lock per csvPath, whether the file has
// been populated yet or not.
async function _ensureFileExists(csvPath) {
  try {
    await fs.access(csvPath)
  } catch {
    await fs.mkdir(path.dirname(csvPath), { recursive: true })
    await fs.writeFile(csvPath, V2_COLUMNS.join(',') + '\n', { flag: 'wx' }).catch(() => {})
  }
}

export async function withCsvLock(csvPath, fn) {
  const prev = _csvLocks.get(csvPath) || Promise.resolve()
  let release
  const next = new Promise((resolve) => { release = resolve })
  const myChain = prev.then(() => next)
  _csvLocks.set(csvPath, myChain)
  try {
    await prev
    // Acquire the cross-process file lock. Retry with exponential backoff
    // so a Python writer that holds the lock for a fraction of a second
    // doesn't cause us to error out; retries capped so an abandoned lock
    // (process killed mid-write) doesn't wedge the server forever —
    // proper-lockfile also auto-recovers stale locks via heartbeat.
    await _ensureFileExists(csvPath)
    const unlock = await lockfile.lock(csvPath, {
      lockfilePath: csvPath + '.lock',
      retries: { retries: 15, minTimeout: 50, maxTimeout: 500, factor: 1.5 },
      stale: 10_000,   // treat a lock with no heartbeat >10s as abandoned
    })
    try {
      return await fn()
    } finally {
      await unlock()
    }
  } finally {
    release()
    // Only clear the map entry if we're still the tail — otherwise a
    // queued-up follow-up is already holding the chain.
    if (_csvLocks.get(csvPath) === myChain) _csvLocks.delete(csvPath)
  }
}

// ── In-memory row cache (stat-mtime invalidated) ───────────────────────────
// The labels.csv is read on every page-load, every image fetch, and every
// save — repeatedly parsing a 10K-row file is the hot path. We keep a single
// in-memory copy keyed by absolute path; if the file's mtime hasn't moved,
// the cache is trusted. Writes refresh the cache with fresh clones of the
// rows they just persisted.
const _rowCache = new Map()  // csvPath → { mtimeMs, headers, rows, byPath }

/** Drop the cache entry for one path, or all of them when called with no arg. */
export function invalidateRowCache(csvPath) {
  if (csvPath) _rowCache.delete(csvPath)
  else _rowCache.clear()
}

async function statMtime(csvPath) {
  try {
    const s = await fs.stat(csvPath)
    return s.mtimeMs
  } catch {
    return null
  }
}

function cloneRows(rows) {
  // Shallow-clone is enough — row values are strings.
  return rows.map((r) => ({ ...r }))
}

function indexByPath(rows) {
  const m = new Map()
  for (const r of rows) if (r.crop_path) m.set(r.crop_path, r)
  return m
}

// ── file I/O ───────────────────────────────────────────────────────────────
/**
 * Read labels.csv (v2). Returns { headers, rows, byPath } where byPath is a
 * Map<crop_path, row> for O(1) updates.
 *
 * Cached across calls — stat.mtime is compared against the cached mtime, so
 * external edits (hand-editing, the Python pipeline appending rows) are picked
 * up on the next call without needing an explicit invalidation.
 *
 * Callers MUST NOT mutate the returned rows — they are shared across readers
 * in the cache window. Use `map` to produce new row objects when patching.
 */
export async function readLabelsCsv(csvPath) {
  const mt = await statMtime(csvPath)
  const cached = _rowCache.get(csvPath)
  if (cached && mt !== null && cached.mtimeMs === mt) {
    return { headers: cached.headers, rows: cached.rows, byPath: cached.byPath }
  }
  let text = ''
  try {
    text = await fs.readFile(csvPath, 'utf8')
  } catch (err) {
    if (err.code === 'ENOENT') {
      return { headers: [...V2_COLUMNS], rows: [], byPath: new Map() }
    }
    throw err
  }
  const { headers, rows } = parseCsv(text)
  const byPath = indexByPath(rows)
  if (mt !== null) _rowCache.set(csvPath, { mtimeMs: mt, headers, rows, byPath })
  return { headers, rows, byPath }
}

/**
 * Atomic write: temp file + rename. Header is V2_COLUMNS unless the caller
 * passes a different column order (e.g. when preserving a legacy header).
 * Refreshes the row cache with a fresh clone of `rows` after a successful
 * rename so the next `readLabelsCsv` skips the parse round-trip.
 */
export async function writeLabelsCsv(csvPath, rows, { columns = V2_COLUMNS } = {}) {
  const dir = path.dirname(csvPath)
  await fs.mkdir(dir, { recursive: true })
  const lines = [columns.join(',')]
  for (const r of rows) lines.push(serialiseRow(r, columns))
  const body = lines.join('\n') + '\n'
  const tmp = csvPath + '.tmp'
  await fs.writeFile(tmp, body, 'utf8')
  await fs.rename(tmp, csvPath)
  const mt = await statMtime(csvPath)
  if (mt !== null) {
    const fresh = cloneRows(rows)
    _rowCache.set(csvPath, {
      mtimeMs: mt,
      headers: [...columns],
      rows: fresh,
      byPath: indexByPath(fresh),
    })
  } else {
    _rowCache.delete(csvPath)
  }
  return rows.length
}

/** Derive the output columns for a write: honour the file's existing header
 *  (so extra columns added by other tools aren't silently dropped) while
 *  ensuring every v2 column is present. Falls back to V2_COLUMNS alone when
 *  the file is empty / missing. */
export function mergeColumns(fileHeaders) {
  if (!fileHeaders || fileHeaders.length === 0) return [...V2_COLUMNS]
  const extras = V2_COLUMNS.filter((c) => !fileHeaders.includes(c))
  return [...fileHeaders, ...extras]
}

/**
 * Update a single row (matched by crop_path) and write back atomically.
 * `patch` merges into the existing row; missing columns stay as-is.
 *
 * Preserves the file's column layout by default — if the CSV had been
 * augmented with extra columns (e.g. a future `quality_score` added by the
 * Python pipeline), those survive the write. Pass `{ preserveHeader: false }`
 * to force V2_COLUMNS only.
 *
 * Returns the updated row (as a fresh object, so callers can safely mutate it).
 */
export async function updateLabelRow(csvPath, cropPath, patch, { preserveHeader = true } = {}) {
  return withCsvLock(csvPath, async () => {
    const { headers, rows, byPath } = await readLabelsCsv(csvPath)
    const existing = byPath.get(cropPath)
    if (!existing) {
      const err = new Error(`No row with crop_path=${cropPath}`)
      err.status = 404
      throw err
    }
    const merged = { ...existing, ...patch }
    for (const c of V2_COLUMNS) {
      if (!(c in merged)) merged[c] = ''
    }
    const updatedRows = rows.map((r) =>
      r.crop_path === cropPath ? merged : r
    )
    const outCols = preserveHeader ? mergeColumns(headers) : V2_COLUMNS
    await writeLabelsCsv(csvPath, updatedRows, { columns: outCols })
    return merged
  })
}

/**
 * Fast path: append-only add a new row. Use for bulk ingestion; prefer
 * updateLabelRow for edits. The lock is NOT re-entrant, so we inline the
 * upsert logic here rather than delegating to updateLabelRow — calling
 * into another withCsvLock from inside a held lock would deadlock.
 */
export async function appendLabelRow(csvPath, row) {
  return withCsvLock(csvPath, async () => {
    const { headers, rows } = await readLabelsCsv(csvPath)
    const existing = rows.find((r) => r.crop_path === row.crop_path)
    if (existing) {
      // Inline the merge-and-write so we don't re-enter the lock.
      const merged = { ...existing, ...row }
      for (const c of V2_COLUMNS) {
        if (!(c in merged)) merged[c] = ''
      }
      const updatedRows = rows.map((r) =>
        r.crop_path === row.crop_path ? merged : r
      )
      await writeLabelsCsv(csvPath, updatedRows, { columns: mergeColumns(headers) })
      return merged
    }
    await writeLabelsCsv(csvPath, [...rows, row], { columns: mergeColumns(headers) })
    return row
  })
}

/** ISO8601 UTC, seconds precision. Matches the Python format. */
export function utcNowIso() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z')
}
