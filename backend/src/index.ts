// CRITICAL: Load .env FIRST, before any other imports!
import dotenv from 'dotenv'
import path from 'path'

const envPath = path.join(process.cwd(), '../.env')
console.log(`[DOTENV] Loading from: ${envPath}`)
const result = dotenv.config({ path: envPath })
if (result.error) {
  console.error(`[DOTENV] ERROR:`, result.error)
} else {
  console.log(`[DOTENV] Loaded successfully`)
}

// Now import everything else
import express, { Request, Response, NextFunction } from 'express'
import cors from 'cors'
import { promises as fs } from 'fs'
import { addRequestId } from './middleware/requestId'
import { errorHandler, notFoundHandler } from './middleware/errorHandler'
import logger, { createRequestLogger } from './utils/logger'
import sharp from 'sharp'
import { annotationService } from './services/annotationService'
import { dashboardStatsService } from './services/dashboardStatsService'
import { activeLearningService } from './services/activeLearningService'

// Wire up cache invalidation
annotationService.onAnnotationSaved = () => {
  dashboardStatsService.invalidateCache()
}

// In-memory record of the image each user most recently loaded. Lets tooling
// (e.g. `GET /api/annotate/current-session`) observe what the live annotator
// is looking at. Resets on restart; last writer wins per userId.
type SessionEntry = { imageId: string; userId: string; source: 'next' | 'direct'; at: number }
const sessionState = new Map<string, SessionEntry>()
function recordSession(userId: string | undefined, imageId: string, source: 'next' | 'direct') {
  const key = userId || 'anonymous'
  sessionState.set(key, { imageId, userId: key, source, at: Date.now() })
}

const app = express()
const port = process.env.PORT || 3001

// ═══════════════════════════════════════════════════════════
// MIDDLEWARE
// ═══════════════════════════════════════════════════════════

app.set('trust proxy', 1)
app.use(cors())
app.use(addRequestId)

// Optional password protection — set ANNOTATOR_PASSWORD in .env to enable.
// Works when the frontend is served from the same origin or with Cloudflare Access.
if (process.env.ANNOTATOR_PASSWORD) {
  app.use((req: Request, res: Response, next: NextFunction) => {
    const auth = req.headers.authorization
    if (auth?.startsWith('Basic ')) {
      const decoded = Buffer.from(auth.slice(6), 'base64').toString()
      const password = decoded.split(':').slice(1).join(':')
      if (password === process.env.ANNOTATOR_PASSWORD) return next()
    }
    res.set('WWW-Authenticate', 'Basic realm="40K Annotator"')
      .status(401).json({ success: false, error: { code: 'UNAUTHORIZED', message: 'Password required' } })
  })
}

// Request logging
app.use((req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)
  log.info(`📥 ${req.method} ${req.path}`)
  next()
})

// Body parsers
app.use(express.json({ limit: '100kb' }))
app.use(express.urlencoded({ limit: '100kb', extended: true }))

// ═══════════════════════════════════════════════════════════
// ANNOTATION ENDPOINTS
// ═══════════════════════════════════════════════════════════

/**
 * GET /api/annotate/images
 *
 * Get the 40K taxonomy (20 canonical factions + their units) for the
 * per-bbox faction + unit pickers. Sourced from scripts/data/units.json,
 * which is the single source of truth wrapped by photoanalyzer.taxonomy
 * on the Python side. Returned shape:
 *
 *     {
 *       factions: ["adepta_sororitas", "adeptus_custodes", ...],
 *       unitsByFaction: {
 *         space_marines: [{ slug: "intercessors", name: "Intercessors" }, ...],
 *         ...
 *       }
 *     }
 *
 * Cached in memory per server boot — units.json is ~300KB and changes
 * rarely (new codex, new units). Manual restart picks up edits.
 */
let _taxonomyCache: { factions: string[]; unitsByFaction: Record<string, Array<{ slug: string; name: string; category?: string }>> } | null = null

async function getTaxonomy() {
  if (_taxonomyCache) return _taxonomyCache
  const unitsPath = path.resolve(__dirname, '../../scripts/data/units.json')
  const raw = await fs.readFile(unitsPath, 'utf-8')
  const data = JSON.parse(raw) as { factions: Record<string, { units?: Array<{ name: string; category?: string }> }> }
  // Slugify a unit name the same way photoanalyzer.taxonomy.slugify does —
  // lowercase, strip Unicode curly quotes (Wahapedia uses them on
  // possessives like "Lion El'jonson"), strip straight apostrophes,
  // spaces → underscores. MUST match the Python exactly or round-trip
  // through labels.csv silently breaks.
  const slugify = (name: string): string =>
    String(name || '')
      .toLowerCase()
      .replace(/\u2018/g, '')
      .replace(/\u2019/g, '')
      .replace(/'/g, '')
      .replace(/ /g, '_')

  const factions = Object.keys(data.factions || {})
  const unitsByFaction: Record<string, Array<{ slug: string; name: string; category?: string }>> = {}
  for (const f of factions) {
    const body = data.factions[f] ?? {}
    unitsByFaction[f] = (body.units || []).map(u => ({
      slug: slugify(u.name),
      name: u.name,
      category: u.category,
    }))
  }
  _taxonomyCache = { factions, unitsByFaction }
  return _taxonomyCache
}

/**
 * Build a small `meta` blob describing an image's provenance for the
 * annotator UI. Always returns `filename`. For CMON-sourced images,
 * follows the symlink at `imagePath` back to its real location, reads
 * the adjacent manifest.json, and pulls out `title` / `artist` /
 * `sourceUrl`. Manifests are parsed once per process; cache by
 * resolved-real path so two views of the same CMON entry share.
 */
const _cmonManifestCache = new Map<string, {
  title?: string; artist?: string; sourceUrl?: string
  score?: number; votes?: number; tags?: string[]
}>()

// gw_shop folder_slug → canonical unit_slug, loaded once on first use.
// Lives at scripts/data/gw_slug_canonical_map.json; built by
// scripts/build_gw_slug_map.py. Empty-string values mean unmapped — the
// walkthrough UI shows a blank slug and the user picks from the
// taxonomy dropdown.
let _gwSlugMap: Map<string, string> | null = null
async function loadGwSlugMap(): Promise<Map<string, string>> {
  if (_gwSlugMap) return _gwSlugMap
  const mapPath = path.join(__dirname, '../../scripts/data/gw_slug_canonical_map.json')
  try {
    const raw = await fs.readFile(mapPath, 'utf-8')
    const obj = JSON.parse(raw) as Record<string, string>
    _gwSlugMap = new Map(Object.entries(obj))
  } catch (e) {
    logger.warn(`gw_slug_canonical_map.json not found at ${mapPath}; walkthrough pre-fill disabled`)
    _gwSlugMap = new Map()
  }
  return _gwSlugMap
}

/** Parse a gw_shop symlink filename → folder_slug. Filenames look like
 *  `ael_shining_spear__99120104071_AELShiningSpearLead.jpg` — everything
 *  before the `__` is the gw_shop folder name. */
function parseGwFolderSlug(filename: string): string | null {
  const sep = filename.indexOf('__')
  if (sep < 0) return null
  return filename.slice(0, sep)
}

/** Look up the canonical unit_slug for a gw_shop image. Returns null if
 *  the image isn't a gw_shop file or the mapping is missing/empty. */
async function suggestedUnitSlugForGwImage(imagePath: string, faction: string): Promise<string | null> {
  const filename = path.basename(imagePath)
  const folderSlug = parseGwFolderSlug(filename)
  if (!folderSlug) return null
  const map = await loadGwSlugMap()
  const canonical = map.get(`${faction}/${folderSlug}`)
  return canonical || null
}

async function buildImageMeta(imagePath: string): Promise<{
  filename: string
  title?: string
  artist?: string
  sourceUrl?: string
  score?: number
  votes?: number
  tags?: string[]
}> {
  const filename = path.basename(imagePath)
  // Only CMON imports are symlinks into scripts/cmon/images/*/<entry>/<view>.jpg.
  // For non-CMON images we just return the filename.
  let realPath = imagePath
  try {
    realPath = await (await import('fs')).promises.realpath(imagePath)
  } catch {
    return { filename }
  }
  if (!realPath.includes('/scripts/cmon/images/')) {
    return { filename }
  }
  const entryDir = path.dirname(realPath)
  const cached = _cmonManifestCache.get(entryDir)
  if (cached) return { filename, ...cached }
  try {
    const raw = await fs.readFile(path.join(entryDir, 'manifest.json'), 'utf-8')
    const m = JSON.parse(raw) as {
      title?: string; tile_title?: string
      artist?: string; tile_artist?: string
      url?: string
      score?: number | string
      votes?: number | string
      tags?: string[]
    }
    // CMON's `score` is 0–10 (community rating). `votes` is the count
    // of raters. `tags` are free-form labels the submitter picked
    // (often include "Science Fiction", "Warhammer 40k", "28mm", unit
    // categories, etc). Useful for the annotator: high score + many
    // votes = quality reference shot; tags sometimes hint at the unit
    // when the title doesn't.
    const scoreNum = typeof m.score === 'number' ? m.score : (m.score ? Number(m.score) : NaN)
    const votesNum = typeof m.votes === 'number' ? m.votes : (m.votes ? Number(m.votes) : NaN)
    const meta: { title?: string; artist?: string; sourceUrl?: string; score?: number; votes?: number; tags?: string[] } = {
      title: m.title || m.tile_title || undefined,
      artist: m.artist || m.tile_artist || undefined,
      sourceUrl: m.url || undefined,
    }
    if (Number.isFinite(scoreNum)) meta.score = scoreNum
    if (Number.isFinite(votesNum)) meta.votes = votesNum
    if (Array.isArray(m.tags) && m.tags.length > 0) meta.tags = m.tags
    _cmonManifestCache.set(entryDir, meta)
    return { filename, ...meta }
  } catch {
    return { filename }
  }
}

app.get('/api/annotate/taxonomy', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  try {
    const taxonomy = await getTaxonomy()
    // Bundle the configured source list (e.g. ["ebay","isolation","cmon"])
    // into the same response so the frontend's source picker doesn't
    // need a second fetch and stays in lockstep with the env var.
    res.json({
      success: true,
      data: { ...taxonomy, sources: annotationService.allowedSources },
      requestId,
    })
  } catch (err) {
    next(err)
  }
})

/**
 * GET /api/annotate/next
 *
 * Get next unannotated image
 */
app.get('/api/annotate/next', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const prioritize = req.query.prioritize === 'true'
    const faction = req.query.faction as string | undefined
    const userId = req.query.userId as string | undefined
    const exclude = req.query.exclude ? (req.query.exclude as string).split(',') : undefined
    // Source filter — comma-separated, validated against allowedSources
    // so a typo'd `?source=cmonn` returns 400 rather than silently giving
    // the unfiltered queue.
    const allowed = new Set(annotationService.allowedSources)
    let sources: string[] | undefined
    if (req.query.source) {
      sources = (req.query.source as string).split(',').map(s => s.trim()).filter(Boolean)
      const bad = sources.filter(s => !allowed.has(s))
      if (bad.length > 0) {
        return res.status(400).json({
          success: false,
          error: `Unknown source(s): ${bad.join(', ')}. Allowed: ${[...allowed].join(', ')}`,
          requestId,
        })
      }
    }
    // Status filter:
    //   `unannotated` (default) — fresh images
    //   `pending`  — annotated but missing unit_slug on at least one bbox
    //   `legacy`   — grandfathered (annotated before unit_slug existed)
    //   `pseudo`   — Phase F1 auto-labels awaiting human box review
    //                (pseudoLabelled: true); saving promotes them out of this bucket
    //   `flagged`  — images user marked unusable (`.skip.json` sidecar);
    //                browse-mode so the user can review + un-flag
    //   `frozen_eval` — Phase C held-out 200; browse-only review surface
    //                (saving still works, but the manifest is the source of
    //                truth — see data/scene_benchmark/eval_200.json)
    //   `all`      — pending > legacy > unannotated (flagged excluded)
    //   `gw_walk`  — Phase B reference walkthrough — gw_shop images sorted
    //                by folder_slug so the user walks unit-by-unit;
    //                response carries a suggested_unit_slug pre-fill from
    //                scripts/data/gw_slug_canonical_map.json
    const rawStatus = (req.query.status as string | undefined) ?? 'unannotated'
    const STATUS_VALUES = ['unannotated', 'pending', 'legacy', 'pseudo', 'flagged', 'frozen_eval', 'all', 'gw_walk'] as const
    if (!STATUS_VALUES.includes(rawStatus as typeof STATUS_VALUES[number])) {
      return res.status(400).json({
        success: false,
        error: `Invalid status '${rawStatus}'. Must be one of: ${STATUS_VALUES.join(', ')}.`,
        requestId,
      })
    }
    const status = rawStatus as typeof STATUS_VALUES[number]
    log.info(`📷 Get next image (status: ${status}, prioritize: ${prioritize}, faction: ${faction || 'all'}, source: ${sources?.join(',') || 'all'}, user: ${userId || 'anonymous'})`)

    const image = await annotationService.getNextImage(prioritize, faction, userId, exclude, sources, status)

    if (!image) {
      log.info(`✅ No more images to annotate`)
      return res.json({
        success: true,
        data: {
          image: null,
          message: 'All images have been annotated!'
        },
        requestId
      })
    }

    // Include full image data in response to avoid a second round-trip.
    // Over ngrok this saves ~500ms per image load.
    const [imageBuffer, metadata, annotation, meta] = await Promise.all([
      fs.readFile(image.imagePath),
      sharp(image.imagePath).metadata(),
      annotationService.getAnnotation(image.imageId),
      buildImageMeta(image.imagePath),
    ])
    const imageBase64 = `data:image/jpeg;base64,${imageBuffer.toString('base64')}`

    log.info(`✅ Next image: ${image.imageId}`)
    recordSession(userId, image.imageId, 'next')

    // If the annotation has a canonical faction (user-corrected), let it
    // win over the folder-derived one for display. File paths stay put;
    // only the label seen by the UI / downstream consumers is updated.
    const effectiveFaction = annotation?.faction || image.faction

    // gw_walk pre-fill — derive folder_slug from the symlink filename,
    // look up canonical unit_slug. UI uses this to populate the unit
    // dropdown so the user just confirms + tightens the bbox. Empty
    // string ↔ no mapping yet; UI shows the raw folder_slug as a hint.
    let suggestedUnitSlug: string | null = null
    let gwFolderSlug: string | null = null
    if (status === 'gw_walk') {
      gwFolderSlug = parseGwFolderSlug(path.basename(image.imagePath))
      suggestedUnitSlug = await suggestedUnitSlugForGwImage(image.imagePath, image.faction)
    }

    res.json({
      success: true,
      data: {
        image: {
          ...image,
          faction: effectiveFaction,
          imageBase64,
          width: metadata.width || 0,
          height: metadata.height || 0,
          meta,   // { filename, title?, artist?, sourceUrl? } — drives the UI header
          // gw_walk-only: walkthrough hints. Both null for other statuses.
          gwFolderSlug,
          suggestedUnitSlug,
        },
        annotation,
      },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to get next image: ${error.message}`)
    next(error)
  }
})

/**
 * GET /api/annotate/image/:imageId
 *
 * Get image data (as base64) and existing annotation
 */
app.get('/api/annotate/image/:imageId', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { imageId } = req.params
    log.info(`📷 Get image data: ${imageId}`)

    // Fast path: use the permanent imagePathMap (populated during first scan).
    // Falls back to a full scan only on cold start before any scan has happened.
    let image = annotationService.getImageMeta(imageId)
    if (!image) {
      const images = await annotationService.getImageList(true)
      const found = images.find(img => img.imageId === imageId)
      if (!found) {
        log.error(`🔴 Image not found: ${imageId}`)
        return res.status(404).json({
          success: false,
          error: { code: 'NOT_FOUND', message: 'Image not found' },
          requestId
        })
      }
      image = found
    }

    // Read image and get metadata in parallel
    const [imageBuffer, metadata, annotation, meta] = await Promise.all([
      fs.readFile(image.imagePath),
      sharp(image.imagePath).metadata(),
      annotationService.getAnnotation(imageId),
      buildImageMeta(image.imagePath),
    ])

    const imageBase64 = `data:image/jpeg;base64,${imageBuffer.toString('base64')}`

    // Annotation-derived faction wins over folder-derived when present.
    const effectiveFaction = annotation?.faction || image.faction

    log.info(`✅ Image data loaded: ${imageId}`)
    recordSession(req.query.userId as string | undefined, imageId, 'direct')

    res.json({
      success: true,
      data: {
        image: {
          imageId,
          ...image,
          faction: effectiveFaction,
          isAnnotated: !!annotation,
          imageBase64,
          width: metadata.width || 0,
          height: metadata.height || 0,
          meta,
        },
        annotation
      },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to get image data: ${error.message}`)
    next(error)
  }
})

/**
 * POST /api/annotate/save
 *
 * Save annotation for an image
 */
app.post('/api/annotate/save', express.json(), async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    log.info(`💾 Save annotation`)

    const annotation = req.body

    // Validate required fields
    if (!annotation.imageId || !annotation.imagePath) {
      log.error(`🔴 Missing required fields`)
      return res.status(400).json({
        success: false,
        error: {
          code: 'INVALID_REQUEST',
          message: 'Missing required fields: imageId, imagePath'
        },
        requestId
      })
    }

    // Run quality checks
    const issues = await annotationService.validateAnnotation(annotation)
    const errors = issues.filter(i => i.type === 'error')
    const warnings = issues.filter(i => i.type === 'warning')

    // Block on errors
    if (errors.length > 0) {
      log.error(`🔴 Annotation has ${errors.length} quality errors`)
      return res.status(400).json({
        success: false,
        errors,
        warnings,
        message: 'Cannot save: annotation has quality errors',
        requestId
      })
    }

    // Save annotation
    await annotationService.saveAnnotation(annotation)

    log.info(`✅ Annotation saved: ${annotation.imageId}${warnings.length > 0 ? ` (${warnings.length} warnings)` : ''}`)

    res.json({
      success: true,
      warnings,  // Return warnings but allow save
      data: {
        imageId: annotation.imageId,
        annotationCount: annotation.annotations?.length || 0
      },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to save annotation: ${error.message}`)
    next(error)
  }
})

/**
 * GET /api/annotate/progress
 *
 * Get annotation progress statistics
 */
app.get('/api/annotate/progress', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    log.info(`📊 Get annotation progress`)

    const progress = await annotationService.getProgress()

    log.info(`✅ Progress: ${progress.annotatedImages}/${progress.totalImages} (${progress.percentComplete.toFixed(2)}%)`)

    res.json({
      success: true,
      data: {
        progress
      },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to get progress: ${error.message}`)
    next(error)
  }
})

/**
 * POST /api/annotate/flag
 *
 * Flag an image as unusable (permanently skip)
 */
app.post('/api/annotate/flag', express.json(), async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { imageId, reason } = req.body

    if (!imageId) {
      res.status(400).json({ success: false, error: { message: 'imageId is required' } })
      return
    }

    await annotationService.flagImage(imageId, reason)
    log.info(`🚫 Flagged image ${imageId} as unusable`)

    res.json({ success: true, data: { imageId, flagged: true }, requestId })
  } catch (error: any) {
    log.error(`🔴 Failed to flag image: ${error.message}`)
    next(error)
  }
})

/**
 * POST /api/annotate/unflag
 *
 * Remove the flagged-unusable mark so the image returns to the queue.
 * Idempotent — posting for an imageId that isn't flagged succeeds
 * silently (no-op). The image itself is never affected, only the
 * sidecar `<imageId>.skip.json` is deleted.
 */
app.post('/api/annotate/unflag', express.json(), async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { imageId } = req.body
    if (!imageId) {
      res.status(400).json({ success: false, error: { message: 'imageId is required' } })
      return
    }
    await annotationService.unflagImage(imageId)
    log.info(`↩ Un-flagged image ${imageId}`)
    res.json({ success: true, data: { imageId, flagged: false }, requestId })
  } catch (error: any) {
    log.error(`🔴 Failed to un-flag image: ${error.message}`)
    next(error)
  }
})

/**
 * GET /api/annotate/who
 *
 * Returns active annotators and the images they currently have reserved.
 * Useful for the dashboard to show who is working on what.
 *
 * @deprecated 2026-05 audit: no frontend caller. Kept as a tooling-only
 *   observability surface (curl + dashboard scripts). Remove only after
 *   confirming no external tooling polls it.
 */
app.get('/api/annotate/who', async (req: Request, res: Response) => {
  const reservations = annotationService.getActiveReservations()
  const byUser: Record<string, number> = {}
  for (const r of reservations) {
    byUser[r.userId] = (byUser[r.userId] || 0) + 1
  }
  res.json({
    success: true,
    data: {
      activeAnnotators: Object.keys(byUser).length,
      byUser,
      reservations: reservations.map(r => ({
        imageId: r.imageId,
        userId: r.userId,
        expiresInMs: r.expiresAt - Date.now()
      }))
    }
  })
})

/**
 * GET /api/annotate/current-session
 *
 * Return the most recently loaded image per user, as tracked by
 * `recordSession` on /next and /image/:imageId. Exists so Claude Code
 * (or other tooling) can answer "what image is the live session on?".
 *
 * @deprecated 2026-05 audit: no frontend caller. Tooling-only. Same
 *   keep-pending-confirmation status as /api/annotate/who.
 */
app.get('/api/annotate/current-session', async (req: Request, res: Response) => {
  const userId = req.query.userId as string | undefined
  const entries = Array.from(sessionState.values()).sort((a, b) => b.at - a.at)
  const current = userId
    ? sessionState.get(userId) ?? null
    : entries[0] ?? null
  res.json({
    success: true,
    data: {
      current,
      all: entries,
    },
  })
})

/**
 * GET /api/annotate/flagged-count
 *
 * Get count of flagged images
 */
app.get('/api/annotate/flagged-count', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const counts = await annotationService.getFlaggedCount()
    res.json({ success: true, data: counts, requestId })
  } catch (error: any) {
    log.error(`🔴 Failed to get flagged count: ${error.message}`)
    next(error)
  }
})

/**
 * GET /api/annotate/sample/:faction
 *
 * Get random annotated sample images for consistency audit
 */
app.get('/api/annotate/sample/:faction', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { faction } = req.params
    const count = parseInt(req.query.count as string) || 9

    log.info(`🔍 Get ${count} sample images for ${faction}`)
    const samples = await annotationService.getSampleImages(faction, count)

    res.json({ success: true, data: { samples }, requestId })
  } catch (error: any) {
    log.error(`🔴 Failed to get samples: ${error.message}`)
    next(error)
  }
})

/**
 * POST /api/annotate/validate-export
 *
 * Validate all annotations before export
 * Returns summary of errors/warnings across dataset
 */
app.post('/api/annotate/validate-export', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    log.info(`🔍 Validate dataset for export`)

    const validationResult = await annotationService.validateAllAnnotations()

    const hasErrors = validationResult.invalidAnnotations > 0

    if (hasErrors) {
      log.warn(`⚠️  Dataset validation found ${validationResult.totalErrors} errors in ${validationResult.invalidAnnotations} annotations`)
    } else {
      log.info(`✅ Dataset validation passed (${validationResult.totalWarnings} warnings)`)
    }

    res.json({
      success: true,
      data: {
        validation: validationResult,
        readyForExport: !hasErrors
      },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Validation failed: ${error.message}`)
    next(error)
  }
})

/**
 * POST /api/annotate/export
 *
 * Export annotations to YOLOv8-pose format
 * Runs validation first and blocks if errors found
 */
app.post('/api/annotate/export', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    log.info(`📦 Export to YOLO format`)

    // Run validation first
    log.info(`🔍 Running pre-export validation...`)
    const validationResult = await annotationService.validateAllAnnotations()

    // Block if errors found
    if (validationResult.invalidAnnotations > 0) {
      log.error(`🔴 Export blocked: ${validationResult.totalErrors} errors in ${validationResult.invalidAnnotations} annotations`)
      return res.status(400).json({
        success: false,
        error: {
          code: 'VALIDATION_FAILED',
          message: `Cannot export: ${validationResult.totalErrors} validation errors found in ${validationResult.invalidAnnotations} annotations`
        },
        validation: validationResult,
        requestId
      })
    }

    // Validation passed, proceed with export
    if (validationResult.totalWarnings > 0) {
      log.warn(`⚠️  Export proceeding with ${validationResult.totalWarnings} warnings`)
    }

    const { outputDir = 'backend/yolo_dataset', trainSplit = 0.8, balanced = false, balancedCap } = req.body

    const result = await annotationService.exportToYOLO(outputDir, trainSplit, { balanced, balancedCap })

    log.info(`✅ Exported ${result.trainImages + result.valImages} annotations`)

    res.json({
      success: true,
      data: {
        export: result,
        validation: {
          totalAnnotations: validationResult.totalAnnotations,
          validAnnotations: validationResult.validAnnotations,
          totalWarnings: validationResult.totalWarnings
        }
      },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Export failed: ${error.message}`)
    next(error)
  }
})

// ═══════════════════════════════════════════════════════════
// MOBILE ANNOTATOR ENDPOINTS
// ═══════════════════════════════════════════════════════════

import archiver from 'archiver'

/**
 * POST /api/mobile/export-batch
 *
 * Export a batch of images as a zip for mobile offline annotation.
 * Resizes images to max 1200px to save phone storage.
 */
app.post('/api/mobile/export-batch', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { faction, limit = 500, includePredictions = false } = req.body || {}
    log.info(`📱 Export batch for mobile (faction: ${faction || 'all'}, limit: ${limit})`)

    const sharp = await import('sharp')

    // Get unannotated images
    let images = await annotationService.getImageList(false)
    if (faction) {
      images = images.filter(img => img.faction === faction)
    }
    images = images.slice(0, limit)

    if (images.length === 0) {
      return res.json({ success: true, data: { message: 'No images to export', count: 0 }, requestId })
    }

    // Build manifest
    const manifest: Array<{
      imageId: string
      faction: string
      filename: string
      width: number
      height: number
    }> = []

    const predictionsMap: Record<string, any[]> = {}

    // Set up zip stream
    res.setHeader('Content-Type', 'application/zip')
    res.setHeader('Content-Disposition', `attachment; filename="batch-${faction || 'all'}-${images.length}.zip"`)

    const archive = archiver('zip', { zlib: { level: 5 } })
    archive.pipe(res)

    for (const img of images) {
      try {
        // Resize to max 1200px
        const resized = await sharp.default(img.imagePath)
          .resize(1200, 1200, { fit: 'inside', withoutEnlargement: true })
          .jpeg({ quality: 85 })
          .toBuffer()

        const metadata = await sharp.default(resized).metadata()
        const ext = 'jpg'
        const filename = `images/${img.imageId}.${ext}`

        archive.append(resized, { name: filename })

        manifest.push({
          imageId: img.imageId,
          faction: img.faction,
          filename,
          width: metadata.width || 0,
          height: metadata.height || 0
        })

        // Optionally include predictions
        if (includePredictions) {
          try {
            const { predictBoxes, isModelAvailable } = await import('./services/yoloInferenceService')
            if (await isModelAvailable()) {
              const result = await predictBoxes(img.imagePath, img.imageId)
              if (result.predictions.length > 0) {
                predictionsMap[img.imageId] = result.predictions.map(p => ({
                  x: Math.round(p.x * (metadata.width || 1)),
                  y: Math.round(p.y * (metadata.height || 1)),
                  width: Math.round(p.width * (metadata.width || 1)),
                  height: Math.round(p.height * (metadata.height || 1)),
                  classLabel: p.classLabel,
                  confidence: p.confidence
                }))
              }
            }
          } catch {
            // Predictions unavailable, skip
          }
        }
      } catch (err) {
        log.warn(`⚠️  Skipped ${img.imageId}: ${err instanceof Error ? err.message : 'unknown error'}`)
      }
    }

    archive.append(JSON.stringify({ images: manifest, exportedAt: new Date().toISOString() }, null, 2), { name: 'manifest.json' })

    if (includePredictions && Object.keys(predictionsMap).length > 0) {
      archive.append(JSON.stringify(predictionsMap, null, 2), { name: 'predictions.json' })
    }

    await archive.finalize()
    log.info(`✅ Exported batch: ${manifest.length} images`)
  } catch (error: any) {
    log.error(`🔴 Failed to export batch: ${error.message}`)
    next(error)
  }
})

/**
 * POST /api/mobile/sync
 *
 * Receive annotations from the mobile annotator.
 * Converts mobile format to backend ImageAnnotation format.
 */
app.post('/api/mobile/sync', express.json({ limit: '10mb' }), async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { annotations } = req.body
    if (!Array.isArray(annotations)) {
      return res.status(400).json({ success: false, error: { code: 'INVALID_REQUEST', message: 'annotations must be an array' }, requestId })
    }

    log.info(`📱 Sync ${annotations.length} annotations from mobile`)

    // Get all images for path lookup
    const allImages = await annotationService.getImageList(true)
    const imageMap = new Map(allImages.map(img => [img.imageId, img]))

    const syncedIds: string[] = []
    const skippedIds: string[] = []
    const failedIds: string[] = []
    const errors: string[] = []

    for (const mobileAnn of annotations) {
      const imageId = mobileAnn.imageId

      // Skip annotations the user explicitly skipped (no bboxes, marked as skipped)
      if (mobileAnn.skipped && (!mobileAnn.bboxes || mobileAnn.bboxes.length === 0)) {
        syncedIds.push(imageId)
        continue
      }

      const image = imageMap.get(imageId)
      if (!image) {
        errors.push(`Image not found: ${imageId}`)
        failedIds.push(imageId)
        continue
      }

      // Skip if already annotated on backend
      const existing = await annotationService.getAnnotation(imageId)
      if (existing) {
        skippedIds.push(imageId)
        continue
      }

      // Get actual image dimensions (original, pre-resize)
      let origWidth = 0
      let origHeight = 0
      try {
        const sharp = await import('sharp')
        const metadata = await sharp.default(image.imagePath).metadata()
        origWidth = metadata.width || 0
        origHeight = metadata.height || 0
      } catch {
        errors.push(`Could not read dimensions for ${imageId}`)
        failedIds.push(imageId)
        continue
      }

      // Mobile bboxes are in resized-image coords (max 1200px).
      // Scale them back to original image coords.
      const mobileWidth = mobileAnn.imageWidth || origWidth
      const mobileHeight = mobileAnn.imageHeight || origHeight
      const scaleX = origWidth / mobileWidth
      const scaleY = origHeight / mobileHeight

      // Convert mobile annotation to backend format
      const backendAnnotation = {
        imageId,
        imagePath: image.imagePath,
        faction: image.faction,
        source: image.source,
        width: origWidth,
        height: origHeight,
        annotations: (mobileAnn.bboxes || []).map((bbox: any) => ({
          id: bbox.id,
          modelBbox: {
            x: Math.round(bbox.x * scaleX),
            y: Math.round(bbox.y * scaleY),
            width: Math.round(bbox.width * scaleX),
            height: Math.round(bbox.height * scaleY)
          },
          classLabel: bbox.classLabel,
          confidence: bbox.confidence,
          validationAction: bbox.fromPrediction ? 'accepted' : undefined,
          originalPrediction: bbox.fromPrediction
        })),
        annotatedAt: mobileAnn.updatedAt,
        annotatedBy: 'mobile-annotator'
      }

      try {
        await annotationService.saveAnnotation(backendAnnotation as any)
        syncedIds.push(imageId)
      } catch (saveErr: any) {
        errors.push(`Failed to save ${imageId}: ${saveErr.message}`)
        failedIds.push(imageId)
      }
    }

    log.info(`✅ Mobile sync: ${syncedIds.length} synced, ${skippedIds.length} skipped, ${failedIds.length} failed`)

    res.json({
      success: true,
      data: { synced: syncedIds.length, skipped: skippedIds.length, syncedIds, skippedIds, failedIds, errors },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to sync: ${error.message}`)
    next(error)
  }
})

/**
 * GET /api/mobile/status
 *
 * Returns annotated image IDs and progress for the mobile app.
 */
app.get('/api/mobile/status', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const allImages = await annotationService.getImageList(true)
    const annotatedIds = allImages.filter(img => img.isAnnotated).map(img => img.imageId)
    const progress = await annotationService.getProgress()

    res.json({
      success: true,
      data: {
        annotatedIds,
        progress
      },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to get mobile status: ${error.message}`)
    next(error)
  }
})

// ═══════════════════════════════════════════════════════════
// GROUNDING DINO PROPOSALS ENDPOINT
// ═══════════════════════════════════════════════════════════

const proposalsDir = path.join(process.cwd(), 'training_data_proposals')

/**
 * GET /api/annotate/proposals/:imageId
 *
 * Get pre-computed Grounding DINO box proposals for an image.
 * These are generated offline by scripts/grounding_dino_propose.py
 * and served as AI suggestions in the annotator.
 */
app.get('/api/annotate/proposals/:imageId', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { imageId } = req.params
    const proposalPath = path.join(proposalsDir, `${imageId}.json`)

    try {
      const raw = await fs.readFile(proposalPath, 'utf-8')
      const proposal = JSON.parse(raw)

      log.info(`Found ${proposal.boxes?.length || 0} DINO proposals for ${imageId}`)

      res.json({
        success: true,
        data: {
          imageId,
          source: 'grounding_dino',
          predictions: (proposal.boxes || []).map((box: any, idx: number) => ({
            id: `dino_${idx}`,
            x: box.x,
            y: box.y,
            width: box.width,
            height: box.height,
            classLabel: 'miniature',
            confidence: box.confidence,
          })),
          inferenceTime: 0,
        },
        requestId,
      })
    } catch {
      // No proposal file — return empty
      res.json({
        success: true,
        data: { imageId, source: 'none', predictions: [], inferenceTime: 0 },
        requestId,
      })
    }
  } catch (error: any) {
    log.error(`Failed to load proposals: ${error.message}`)
    next(error)
  }
})

// ═══════════════════════════════════════════════════════════
// YOLO INFERENCE ENDPOINT
// ═══════════════════════════════════════════════════════════

import { predictBoxes, isModelAvailable, detectAndSummarize } from './services/yoloInferenceService'
import multer from 'multer'

const upload = multer({ dest: '/tmp/battlescanner-uploads/', limits: { fileSize: 20 * 1024 * 1024 } })

/**
 * GET /api/annotate/predict/:imageId
 *
 * Get AI predictions for an image using the trained YOLO model
 */
app.get('/api/annotate/predict/:imageId', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { imageId } = req.params
    log.info(`🤖 Predicting boxes for: ${imageId}`)

    // Check if model is available
    const modelReady = await isModelAvailable()
    if (!modelReady) {
      log.error(`🔴 YOLO model not found`)
      return res.status(503).json({
        success: false,
        error: {
          code: 'MODEL_NOT_AVAILABLE',
          message: 'YOLO model not found. Please ensure best.pt is in runs/ directory.'
        },
        requestId
      })
    }

    // Get image path
    const images = await annotationService.getImageList(true)
    const image = images.find(img => img.imageId === imageId)

    if (!image) {
      log.error(`🔴 Image not found: ${imageId}`)
      return res.status(404).json({
        success: false,
        error: {
          code: 'NOT_FOUND',
          message: 'Image not found'
        },
        requestId
      })
    }

    // Run inference
    const result = await predictBoxes(image.imagePath, imageId)

    log.info(`✅ Predicted ${result.predictions.length} boxes in ${result.inferenceTime}ms`)

    res.json({
      success: true,
      data: result,
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Prediction failed: ${error.message}`)
    next(error)
  }
})

// ═══════════════════════════════════════════════════════════
// CONSUMER DETECTION ENDPOINT
// ═══════════════════════════════════════════════════════════

/**
 * POST /api/detect
 *
 * Consumer endpoint: upload an image, get detected miniatures grouped by faction
 */
app.post('/api/detect', upload.single('image'), async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    log.info(`🔍 Consumer detection request`)

    if (!req.file) {
      return res.status(400).json({
        success: false,
        error: { code: 'NO_IMAGE', message: 'No image uploaded' },
        requestId
      })
    }

    const modelReady = await isModelAvailable()
    if (!modelReady) {
      return res.status(503).json({
        success: false,
        error: { code: 'MODEL_NOT_AVAILABLE', message: 'Detection model is not available' },
        requestId
      })
    }

    // Rename file with proper extension so YOLO recognizes it as an image
    const fsPromises = await import('fs/promises')
    const ext = path.extname(req.file.originalname) || '.jpg'
    const imagePath = req.file.path + ext
    await fsPromises.rename(req.file.path, imagePath)

    const result = await detectAndSummarize(imagePath)

    log.info(`✅ Detected ${result.totalDetected} miniatures in ${result.inferenceTimeMs}ms`)

    // Clean up uploaded file
    await fsPromises.unlink(imagePath).catch(() => {})

    res.json({
      success: true,
      data: result,
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Detection failed: ${error.message}`)
    // Clean up on error — try both with and without extension
    if (req.file) {
      const fsP = await import('fs/promises')
      const ext2 = path.extname(req.file.originalname) || '.jpg'
      await fsP.unlink(req.file.path + ext2).catch(() => {})
      await fsP.unlink(req.file.path).catch(() => {})
    }
    next(error)
  }
})

// ═══════════════════════════════════════════════════════════
// DASHBOARD ENDPOINT
// ═══════════════════════════════════════════════════════════

/**
 * GET /api/dashboard/stats
 *
 * Get annotation quality dashboard statistics
 */
app.get('/api/dashboard/stats', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    log.info(`📊 Get dashboard stats`)

    const stats = await dashboardStatsService.getStats()

    log.info(`✅ Dashboard stats: ${stats.totalAnnotations} annotations, ${stats.totalBoxes} boxes`)

    res.json({
      success: true,
      data: stats,
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to get dashboard stats: ${error.message}`)
    next(error)
  }
})

// ═══════════════════════════════════════════════════════════
// ACTIVE LEARNING ENDPOINTS
// ═══════════════════════════════════════════════════════════

/**
 * POST /api/active-learning/start-batch
 *
 * Start background batch inference to score unannotated images
 */
app.post('/api/active-learning/start-batch', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { factions, limit } = req.body || {}
    log.info(`🤖 Start batch inference (factions: ${factions || 'all'}, limit: ${limit || 'all'})`)

    // Get unannotated images
    let images = await annotationService.getImageList(false)

    // Filter by factions if specified
    if (factions && Array.isArray(factions) && factions.length > 0) {
      images = images.filter(img => factions.includes(img.faction))
    }

    if (images.length === 0) {
      return res.json({
        success: true,
        data: { message: 'No unannotated images to process' },
        requestId
      })
    }

    activeLearningService.startBatchInference(images, limit)

    res.json({
      success: true,
      data: { message: `Started batch inference on ${Math.min(images.length, limit || images.length)} images` },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to start batch inference: ${error.message}`)
    next(error)
  }
})

/**
 * GET /api/active-learning/status
 *
 * Get batch inference progress and total scored images
 */
app.get('/api/active-learning/status', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const progress = activeLearningService.getBatchProgress()
    const totalScored = activeLearningService.getTotalScored()

    res.json({
      success: true,
      data: {
        ...progress,
        totalScored
      },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to get active learning status: ${error.message}`)
    next(error)
  }
})

// ═══════════════════════════════════════════════════════════
// HEALTH CHECK
// ═══════════════════════════════════════════════════════════

app.get('/api/health', async (_req: Request, res: Response) => {
  const modelLoaded = await isModelAvailable()
  res.json({ status: 'ok', modelLoaded })
})

// ═══════════════════════════════════════════════════════════
// REFERENCE GALLERY ENDPOINTS (image collection review UI)
// ═══════════════════════════════════════════════════════════

// Accepted clean images: clean_references/{faction}/clean/ (flat, prefixed by unit slug)
const cleanRefsDir = path.join(process.cwd(), '../clean_references')
// Unreviewed scraped candidates
const galleryCandidatesDir = path.join(process.cwd(), 'training_data_candidates')

const IMAGE_EXT_RE = /\.(jpg|jpeg|png|webp)$/i

async function listImages(dir: string): Promise<string[]> {
  try {
    const files = await fs.readdir(dir)
    return files.filter(f => IMAGE_EXT_RE.test(f)).sort()
  } catch {
    return []
  }
}

/** GET /api/references/coverage — full coverage report */
app.get('/api/references/coverage', async (_req: Request, res: Response) => {
  try {
    const raw = await fs.readFile(path.join(galleryCandidatesDir, 'coverage.json'), 'utf-8')
    res.json({ success: true, data: JSON.parse(raw) })
  } catch {
    res.status(404).json({ success: false, error: { message: 'Run: python scripts/generate_coverage.py' } })
  }
})

/** GET /api/references/candidates/:faction/:unit — list candidate images */
app.get('/api/references/candidates/:faction/:unit', async (req: Request, res: Response) => {
  const { faction, unit } = req.params
  const images = await listImages(path.join(galleryCandidatesDir, faction, unit))
  res.json({ success: true, data: { images } })
})

/** GET /api/references/gallery/:faction/:unit — list accepted images (flat dir, filtered by unit prefix) */
app.get('/api/references/gallery/:faction/:unit', async (req: Request, res: Response) => {
  const { faction, unit } = req.params
  const factionDirMap: Record<string, string> = {
    astra_militarum: 'imperial_guard',
    craftworld_aeldari: 'eldar',
    adeptus_custodes: 'custodes',
  }
  const fDir = factionDirMap[faction] || faction
  const dir = path.join(cleanRefsDir, fDir, 'clean')
  try {
    const files = await fs.readdir(dir)
    const images = files.filter(f => f.startsWith(unit + '_') && IMAGE_EXT_RE.test(f)).sort()
    res.json({ success: true, data: { images } })
  } catch {
    res.json({ success: true, data: { images: [] } })
  }
})

/** GET /api/references/image/candidates/:faction/:unit/:filename — serve candidate image */
app.get('/api/references/image/candidates/:faction/:unit/:filename', (req: Request, res: Response) => {
  const { faction, unit, filename } = req.params
  const filePath = path.join(galleryCandidatesDir, faction, unit, filename)
  res.sendFile(filePath, (err) => { if (err) res.status(404).end() })
})

/** GET /api/references/image/gallery/:faction/:unit/:filename — serve accepted image */
app.get('/api/references/image/gallery/:faction/:unit/:filename', (req: Request, res: Response) => {
  const { faction, unit, filename } = req.params
  const factionDirMap: Record<string, string> = {
    astra_militarum: 'imperial_guard',
    craftworld_aeldari: 'eldar',
    adeptus_custodes: 'custodes',
  }
  const fDir = factionDirMap[faction] || faction
  const filePath = path.join(cleanRefsDir, fDir, 'clean', filename)
  res.sendFile(filePath, (err) => { if (err) res.status(404).end() })
})

/** POST /api/references/accept — move candidate to clean_references/{faction}/clean/ (flat) */
app.post('/api/references/accept', express.json(), async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { faction, unit, filename } = req.body
    const factionDirMap: Record<string, string> = {
      astra_militarum: 'imperial_guard',
      craftworld_aeldari: 'eldar',
      adeptus_custodes: 'custodes',
    }
    const fDir = factionDirMap[faction] || faction
    const src = path.join(galleryCandidatesDir, faction, unit, filename)
    const destDir = path.join(process.cwd(), '../clean_references', fDir, 'clean')
    await fs.mkdir(destDir, { recursive: true })
    await fs.rename(src, path.join(destDir, filename))
    res.json({ success: true })
  } catch (error: any) {
    next(error)
  }
})

/** POST /api/references/reject — delete candidate */
app.post('/api/references/reject', express.json(), async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { faction, unit, filename } = req.body
    await fs.unlink(path.join(galleryCandidatesDir, faction, unit, filename))
    res.json({ success: true })
  } catch (error: any) {
    next(error)
  }
})

// ═══════════════════════════════════════════════════════════
// CONSUMER FEEDBACK ENDPOINT
// ═══════════════════════════════════════════════════════════

app.post('/api/consumer/feedback', express.json(), async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    const { feedback } = req.body
    if (!Array.isArray(feedback) || feedback.length === 0) {
      return res.status(400).json({
        success: false,
        error: { code: 'INVALID_REQUEST', message: 'feedback must be a non-empty array' },
        requestId
      })
    }

    log.info(`📝 Consumer feedback: ${feedback.length} items`)

    // Ensure output directory exists
    const feedbackDir = path.join(process.cwd(), 'consumer_feedback')
    await fs.mkdir(feedbackDir, { recursive: true })

    // Write feedback to JSON file with timestamp
    const filename = `feedback-${Date.now()}.json`
    await fs.writeFile(
      path.join(feedbackDir, filename),
      JSON.stringify({ feedback, receivedAt: new Date().toISOString() }, null, 2)
    )

    log.info(`✅ Saved consumer feedback to ${filename}`)

    res.json({ success: true, data: { saved: feedback.length }, requestId })
  } catch (error: any) {
    log.error(`🔴 Failed to save feedback: ${error.message}`)
    next(error)
  }
})

// ═══════════════════════════════════════════════════════════
// STATIC FRONTEND (production / shared deployment)
// ═══════════════════════════════════════════════════════════

// Serve the built frontend from backend so friends only need one URL.
// Build the frontend first: cd frontend && VITE_API_URL=<your-url> npm run build
// The dist folder will be at ../frontend/dist relative to the backend working directory.
const frontendDist = path.join(process.cwd(), '../frontend/dist')
app.use(express.static(frontendDist))

// SPA fallback — return index.html for any non-API route so React Router works
app.get(/^(?!\/api).*/, (req: Request, res: Response) => {
  res.sendFile(path.join(frontendDist, 'index.html'))
})

// ═══════════════════════════════════════════════════════════
// ERROR HANDLING
// ═══════════════════════════════════════════════════════════

app.use(notFoundHandler)
app.use(errorHandler)

// ═══════════════════════════════════════════════════════════
// SERVER STARTUP
// ═══════════════════════════════════════════════════════════

;(async () => {
  try {
    // Initialize annotation service
    logger.info(`📝 Initializing annotation service...`)
    await annotationService.initialize()
    logger.info(`✅ Annotation service initialized`)

    // Start server
    app.listen(port, () => {
      logger.info(`═══════════════════════════════════════`)
      logger.info(`🚀 Server Started Successfully`)
      logger.info(`═══════════════════════════════════════`)
      logger.info(`Port: ${port}`)
      logger.info(`Environment: ${process.env.NODE_ENV || 'development'}`)
      logger.info(`Frontend: http://localhost:5173`)
      logger.info(`Backend: http://localhost:${port}`)
      logger.info(`Logs directory: ${path.join(process.cwd(), 'logs')}`)
      logger.info(`═══════════════════════════════════════`)
    })
  } catch (error) {
    logger.error(`🔴 Failed to start server: ${error}`)
    process.exit(1)
  }
})()
