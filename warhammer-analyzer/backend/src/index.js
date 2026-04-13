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
  selfCheck as labellingSelfCheck,
} from './services/labellingService.js'
import { getServerConfig, validateConfig } from './config/pipeline.js'
import { logger } from './utils/logger.js'

// ─── Startup validation ──────────────────────────────────────────────

const configErrors = validateConfig()
if (configErrors.length) {
  console.error('❌ Configuration errors — fix your .env before starting:')
  for (const err of configErrors) console.error(`   - ${err}`)
  process.exit(1)
}

const { port, maxUploadBytes } = getServerConfig()

// ─── Middleware ───────────────────────────────────────────────────────

const app = express()
app.use(cors())
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
    const crops = await listCrops()
    const unlabelled = crops.filter((c) => !c.labelled).length
    res.json({
      success: true,
      requestId: req.id,
      data: {
        total: crops.length,
        labelled: crops.length - unlabelled,
        unlabelled,
        crops: crops.map(({ absPath, ...rest }) => rest), // don't leak absolute paths
      },
    })
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
    const { unit_slug, notes } = req.body || {}
    const saved = await saveLabel(req.params.id, { unit_slug, notes })
    res.json({ success: true, requestId: req.id, data: saved })
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
      logger.info(`   Labelling: enabled (${s.cropsDir})`)
    } else if (s.enabled) {
      logger.warn(`   Labelling: enabled but ${s.reason}`)
    }
  })
})
