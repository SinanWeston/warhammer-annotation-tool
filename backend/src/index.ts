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
import { annotationService } from './services/annotationService'
import { dashboardStatsService } from './services/dashboardStatsService'
import { activeLearningService } from './services/activeLearningService'

// Wire up cache invalidation
annotationService.onAnnotationSaved = () => {
  dashboardStatsService.invalidateCache()
}

const app = express()
const port = process.env.PORT || 3001

// ═══════════════════════════════════════════════════════════
// MIDDLEWARE
// ═══════════════════════════════════════════════════════════

app.set('trust proxy', 1)
app.use(cors())
app.use(addRequestId)

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
 * Get list of all images with annotation status
 */
app.get('/api/annotate/images', async (req: Request, res: Response, next: NextFunction) => {
  const requestId = (req as any).id
  const log = createRequestLogger(requestId)

  try {
    log.info(`📋 Get image list`)

    const includeDetails = req.query.details === 'true'
    const images = await annotationService.getImageList(includeDetails)

    log.info(`✅ Retrieved ${images.length} images`)

    res.json({
      success: true,
      data: {
        images,
        totalCount: images.length
      },
      requestId
    })
  } catch (error: any) {
    log.error(`🔴 Failed to get image list: ${error.message}`)
    next(error)
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
    log.info(`📷 Get next unannotated image (prioritize: ${prioritize}, faction: ${faction || 'all'})`)

    const image = await annotationService.getNextImage(prioritize, faction)

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

    log.info(`✅ Next image: ${image.imageId}`)

    res.json({
      success: true,
      data: {
        image
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

    // Get image from list
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

    // Read image as base64
    const imageBuffer = await fs.readFile(image.imagePath)
    const imageBase64 = `data:image/jpeg;base64,${imageBuffer.toString('base64')}`

    // Get dimensions
    const sharp = await import('sharp')
    const metadata = await sharp.default(image.imagePath).metadata()

    // Get existing annotation if any
    const annotation = await annotationService.getAnnotation(imageId)

    log.info(`✅ Image data loaded: ${imageId}`)

    res.json({
      success: true,
      data: {
        image: {
          ...image,
          imageBase64,
          width: metadata.width || 0,
          height: metadata.height || 0
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
