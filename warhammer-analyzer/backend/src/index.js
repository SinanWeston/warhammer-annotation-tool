/**
 * Warhammer Analyzer Server
 *
 * Express server exposing two features:
 *   1. Original three-pass analysis pipeline (/api/analyze)
 *   2. AI-assisted labelling (/api/labelling/*) — used to hand-label
 *      the scripts/phase1/crops/ set with LLM suggestions.
 */

import 'dotenv/config'
import express from 'express'
import cors from 'cors'
import multer from 'multer'
import path from 'node:path'
import fs from 'node:fs/promises'
import { detectMiniatures } from './services/detectionService.js'
import { classifyMiniatures } from './services/classificationService.js'
import { validateClassifications } from './services/validationService.js'
import {
  listCrops,
  resolveCropPath,
  suggestForCrop,
  saveLabel,
  listFactions,
  listUnitsForFaction,
  resolveSceneImagePath,
  redrawCrops,
  redrawSceneView,
  editCropBbox,
  selfCheck as labellingSelfCheck,
} from './services/labellingService.js'
import { getServerConfig, validateConfig } from './config/pipeline.js'
import { logger } from './utils/logger.js'
import { VALID_SOURCES } from './services/labelsCsvService.js'

// ─── Startup validation ──────────────────────────────────────────────

const configErrors = validateConfig()
if (configErrors.length) {
  console.error('❌ Configuration errors — fix your .env before starting:')
  for (const err of configErrors) console.error(`   - ${err}`)
  process.exit(1)
}

const { port, maxUploadBytes, frontendPort } = getServerConfig()

// ─── Middleware ───────────────────────────────────────────────────────

const app = express()
// Tight CORS: only the bundled static-file server (and the API itself, so
// tools like curl hitting the API on the same port keep working) are
// allowed. Wide-open CORS + mutating endpoints meant any page open in the
// user's browser could silently POST to /api/labelling/.../label and
// poison the CSV — classic localhost drive-by.
const allowedOrigins = new Set([
  `http://localhost:${frontendPort}`,
  `http://127.0.0.1:${frontendPort}`,
  `http://localhost:${port}`,
  `http://127.0.0.1:${port}`,
])
app.use(cors({
  origin: (origin, cb) => {
    // No Origin header (same-origin fetches, curl) — allow.
    if (!origin) return cb(null, true)
    if (allowedOrigins.has(origin)) return cb(null, true)
    cb(new Error(`CORS blocked: ${origin}`))
  },
}))
app.use(express.json({ limit: '2mb' }))

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: maxUploadBytes, files: 1 },
  fileFilter: (_req, file, cb) => {
    if (/^image\/(jpe?g|png|webp)$/i.test(file.mimetype)) return cb(null, true)
    cb(new Error(`Unsupported file type: ${file.mimetype}. Allowed: image/jpeg, image/png, image/webp`))
  },
})

function makeRequestId() {
  return `req_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`
}

// Request logger — stamps an id, logs every request.
app.use((req, _res, next) => {
  req.id = makeRequestId()
  logger.info(`[${req.id}] ${req.method} ${req.path}`)
  next()
})

// ─── Health ──────────────────────────────────────────────────────────

app.get('/api/health', async (_req, res) => {
  const labelling = await labellingSelfCheck()
  res.json({ status: 'ok', service: 'warhammer-analyzer', labelling })
})

// ─── Analysis pipeline (legacy three-pass) ───────────────────────────

app.post('/api/analyze', upload.single('image'), async (req, res) => {
  const requestId = req.id
  try {
    if (!req.file) {
      return res.status(400).json({ success: false, requestId, error: 'No image file provided' })
    }

    const imageBuffer = req.file.buffer
    const pipelineStart = Date.now()

    logger.info(`[${requestId}] PASS 1: Detection`)
    const {
      detections,
      authorityCount,
      metadata: detectionMetadata,
    } = await detectMiniatures(imageBuffer)
    logger.info(`[${requestId}] PASS 1: ${authorityCount} detections`)

    logger.info(`[${requestId}] PASS 2: Classification`)
    const {
      classifications,
      metadata: classificationMetadata,
    } = await classifyMiniatures(imageBuffer, detections, authorityCount)

    logger.info(`[${requestId}] PASS 3: Validation`)
    const {
      validatedClassifications,
      metadata: validationMetadata,
    } = await validateClassifications(imageBuffer, detections, classifications, authorityCount)

    const results = []
    const summary = new Map()
    for (const detection of detections) {
      const classification = validatedClassifications.get(detection.id)
      results.push({
        id: detection.id,
        bbox: detection.bbox,
        unit: classification.unit,
        faction: classification.faction,
        confidence: classification.confidence,
        tier: classification.tier,
        triangulated: classification.triangulated || false,
        disagreement: classification.disagreement || false,
      })
      const key = `${classification.faction}::${classification.unit}`
      if (!summary.has(key)) {
        summary.set(key, { unit: classification.unit, faction: classification.faction, count: 0 })
      }
      summary.get(key).count++
    }

    if (results.length !== authorityCount) {
      throw new Error(`Count integrity failed: expected ${authorityCount}, got ${results.length}`)
    }

    const pipelineElapsed = Date.now() - pipelineStart
    logger.info(`[${requestId}] ✓ Analysis complete: ${authorityCount} minis in ${pipelineElapsed}ms`)

    res.json({
      success: true,
      requestId,
      data: {
        detections: results,
        summary: { totalCount: authorityCount, models: [...summary.values()] },
        metadata: {
          processingTimeMs: pipelineElapsed,
          detection: detectionMetadata,
          classification: classificationMetadata,
          validation: validationMetadata,
        },
      },
    })
  } catch (err) {
    logger.error(`[${requestId}] analyze failed:`, err)
    res.status(500).json({
      success: false,
      requestId,
      error: err.message,
      stack: process.env.NODE_ENV === 'development' ? err.stack : undefined,
    })
  }
})

// ─── Labelling mode ──────────────────────────────────────────────────

app.get('/api/labelling/status', async (req, res, next) => {
  try {
    res.json({ success: true, requestId: req.id, data: await labellingSelfCheck() })
  } catch (err) {
    next(err)
  }
})

app.get('/api/labelling/crops', async (req, res, next) => {
  try {
    const rawSource = req.query.source || null
    let sourceFilter = null
    if (rawSource) {
      const parts = String(rawSource).split(',').map((s) => s.trim()).filter(Boolean)
      const bad = parts.filter((p) => !VALID_SOURCES.has(p))
      if (bad.length) {
        return res.status(400).json({
          success: false, requestId: req.id,
          error: `unknown source(s): ${bad.join(', ')}. valid: ${[...VALID_SOURCES].join(', ')}`,
        })
      }
      sourceFilter = parts
    }
    const unlabelledOnly = req.query.unlabelled === 'true'
    const auditOnly = req.query.audit === 'true'
    // Clamp limit to a sane upper bound — a runaway ?limit=1e9 would otherwise
    // allocate a huge response and read the entire CSV into JSON.
    let limit = null
    if (req.query.limit != null && req.query.limit !== '') {
      const n = parseInt(req.query.limit, 10)
      if (!Number.isInteger(n) || n <= 0) {
        return res.status(400).json({
          success: false, requestId: req.id,
          error: 'limit must be a positive integer',
        })
      }
      limit = Math.min(n, 5000)
    }
    // withContext defaults on; expensive for large lists without filters, but
    // the manifest cache makes repeat calls cheap.
    const withContext = req.query.context !== 'false'
    const crops = await listCrops({ sourceFilter, unlabelledOnly, auditOnly, limit, withContext })
    const unlabelled = crops.filter((c) => !c.labelled).length
    res.json({
      success: true,
      requestId: req.id,
      data: {
        total: crops.length,
        labelled: crops.length - unlabelled,
        unlabelled,
        crops: crops.map(({ absPath, ...rest }) => rest),
      },
    })
  } catch (err) {
    next(err)
  }
})

app.get('/api/labelling/factions', async (req, res, next) => {
  try {
    const factions = await listFactions()
    res.json({ success: true, requestId: req.id, data: { factions } })
  } catch (err) {
    next(err)
  }
})

app.get('/api/labelling/units', async (req, res, next) => {
  try {
    const faction = String(req.query.faction || '').trim()
    if (!faction) {
      return res.status(400).json({
        success: false, requestId: req.id,
        error: 'query param `faction` required',
      })
    }
    const units = await listUnitsForFaction(faction)
    res.json({ success: true, requestId: req.id, data: { faction, units } })
  } catch (err) {
    next(err)
  }
})

// Serve the original CMON scene image for a given (instance_id, view_idx).
// URL shape: /api/labelling/scenes/cmon:475293/0/image
app.get('/api/labelling/scenes/:instance_id/:view_idx/image', async (req, res, next) => {
  try {
    const inst = decodeURIComponent(req.params.instance_id)
    const viewIdx = parseInt(req.params.view_idx, 10)
    if (!Number.isInteger(viewIdx) || viewIdx < 0) {
      return res.status(400).json({ success: false, error: 'invalid view_idx' })
    }
    const abs = await resolveSceneImagePath(inst, viewIdx)
    if (!abs) {
      return res.status(404).json({
        success: false, error: `no scene for ${inst} view=${viewIdx}`,
      })
    }
    res.sendFile(abs)
  } catch (err) {
    next(err)
  }
})

app.get('/api/labelling/crops/:id/image', async (req, res, next) => {
  try {
    const crop = await resolveCropPath(req.params.id)
    res.sendFile(crop.absPath)
  } catch (err) {
    next(err)
  }
})

app.post('/api/labelling/crops/:id/suggest', async (req, res, next) => {
  try {
    const result = await suggestForCrop(req.params.id)
    res.json({ success: true, requestId: req.id, data: result })
  } catch (err) {
    next(err)
  }
})

app.post('/api/labelling/crops/:id/label', async (req, res, next) => {
  try {
    const { unit_slug, notes, faction, labeller, status, copy_to_siblings } = req.body || {}
    const saved = await saveLabel(req.params.id, {
      unit_slug, notes, faction, labeller, status, copy_to_siblings,
    })
    res.json({ success: true, requestId: req.id, data: saved })
  } catch (err) {
    next(err)
  }
})

// Redraw bboxes (per-crop variant): mark the original crop as bad + extract
// new crops from the source scene. Kept for backward-compat with older UI.
app.post('/api/labelling/crops/:id/redraw', async (req, res, next) => {
  try {
    const { bboxes, labeller } = req.body || {}
    const result = await redrawCrops(req.params.id, bboxes, labeller)
    res.json({ success: true, requestId: req.id, data: result })
  } catch (err) {
    next(err)
  }
})

// Edit the bbox of a single crop in-place. Unlike redraw this does NOT
// mark siblings bad — it rewrites just the clicked row's JPEG + notes.
// Body: { bbox: {x,y,w,h}, labeller?, faction?, unit_slug?, status? }
app.patch('/api/labelling/crops/:id/bbox', async (req, res, next) => {
  try {
    const { bbox, labeller, faction, unit_slug, status } = req.body || {}
    const result = await editCropBbox(req.params.id, bbox, { labeller, faction, unit_slug, status })
    res.json({ success: true, requestId: req.id, data: result })
  } catch (err) {
    next(err)
  }
})

// Redraw bboxes (per-scene variant): works on any (instance, view) even when
// no crops exist for that view. Used by the multi-view redraw modal.
app.post('/api/labelling/scenes/:instance_id/:view_idx/redraw', async (req, res, next) => {
  try {
    const inst = decodeURIComponent(req.params.instance_id)
    const vi = parseInt(req.params.view_idx, 10)
    const { bboxes, labeller, replace_crop_id } = req.body || {}
    const result = await redrawSceneView(inst, vi, bboxes, labeller, {
      replaceCropId: replace_crop_id,
    })
    res.json({ success: true, requestId: req.id, data: result })
  } catch (err) {
    next(err)
  }
})

// ─── Error handlers ──────────────────────────────────────────────────

app.use((err, req, res, _next) => {
  const status = err.status || 500
  const requestId = req.id || 'no-request-id'
  if (status >= 500) logger.error(`[${requestId}] ${err.message}`, err)
  else logger.warn(`[${requestId}] ${status}: ${err.message}`)
  res.status(status).json({
    success: false,
    requestId,
    error: err.message,
    stack: process.env.NODE_ENV === 'development' ? err.stack : undefined,
  })
})

// ─── Boot ────────────────────────────────────────────────────────────

app.listen(port, () => {
  logger.info(`🚀 Warhammer Analyzer running on http://localhost:${port}`)
  logger.info(`   Upload limit: ${Math.round(maxUploadBytes / 1024 / 1024)} MB`)
  logger.info(`   Providers: ${process.env.DETECTION_PROVIDER || 'openrouter'} (detection), multi-tier ${process.env.ENABLE_MULTI_TIER !== 'false' ? 'on' : 'off'}`)
  labellingSelfCheck().then((s) => {
    if (s.enabled && s.healthy) {
      logger.info(`   Labelling: enabled (${s.labelsCsvV2})`)
    } else if (s.enabled) {
      logger.warn(`   Labelling: enabled but ${s.reason}`)
    }
  })
})
