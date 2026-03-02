/**
 * Active Learning Service
 *
 * Manages confidence scores for unannotated images and prioritizes
 * annotation order by serving the least-confident images first.
 *
 * - Spawns a single Python process that loads the YOLO model once
 * - Parses JSON-lines output for real-time progress
 * - Writes scores atomically (temp file + rename)
 * - Falls back to default ordering if no scores exist
 */

import { spawn, ChildProcess } from 'child_process'
import fs from 'fs/promises'
import path from 'path'
import logger from '../utils/logger'

interface ConfidenceScore {
  maxConfidence: number
  avgConfidence: number
  numPredictions: number
}

interface BatchProgress {
  running: boolean
  processed: number
  total: number
}

class ActiveLearningService {
  private scoresPath: string
  private scores: Record<string, ConfidenceScore> = {}
  private scoresLoaded: boolean = false

  private batchProcess: ChildProcess | null = null
  private batchProgress: BatchProgress = { running: false, processed: 0, total: 0 }

  private modelPath: string
  private pythonPath: string
  private scriptPath: string

  constructor() {
    this.scoresPath = path.join(__dirname, '../../confidence_scores.json')
    this.modelPath = path.join(__dirname, '../../../runs/yolo11_colab_best.pt')
    this.pythonPath = path.join(__dirname, '../../../yolo_env/bin/python3')
    this.scriptPath = path.join(__dirname, './batchYoloInference.py')
  }

  /**
   * Load scores from disk if not already loaded
   */
  private async ensureScoresLoaded(): Promise<void> {
    if (this.scoresLoaded) return

    try {
      const data = await fs.readFile(this.scoresPath, 'utf-8')
      this.scores = JSON.parse(data)
      this.scoresLoaded = true
      logger.info(`📊 Loaded ${Object.keys(this.scores).length} confidence scores`)
    } catch {
      this.scores = {}
      this.scoresLoaded = true
    }
  }

  /**
   * Write scores atomically (temp file + rename)
   */
  private async writeScores(): Promise<void> {
    const tmpPath = this.scoresPath + '.tmp'
    await fs.writeFile(tmpPath, JSON.stringify(this.scores, null, 2), 'utf-8')
    await fs.rename(tmpPath, this.scoresPath)
  }

  /**
   * Start batch inference on a set of images
   */
  startBatchInference(
    images: Array<{ imageId: string; imagePath: string }>,
    limit?: number
  ): void {
    if (this.batchProcess) {
      logger.warn('⚠️ Batch inference already running')
      return
    }

    const imagesToProcess = limit ? images.slice(0, limit) : images

    this.batchProgress = {
      running: true,
      processed: 0,
      total: imagesToProcess.length
    }

    // Create a temp file with image paths
    const listPath = this.scoresPath + '.imagelist.tmp'
    const imagePathMap = new Map<string, string>() // imagePath -> imageId

    const lines: string[] = []
    for (const img of imagesToProcess) {
      lines.push(img.imagePath)
      imagePathMap.set(img.imagePath, img.imageId)
    }

    // Write image list and start Python process
    fs.writeFile(listPath, lines.join('\n'), 'utf-8').then(() => {
      this.ensureScoresLoaded().then(() => {
        logger.info(`🤖 Starting batch inference on ${imagesToProcess.length} images`)

        const python = spawn(this.pythonPath, [this.scriptPath, this.modelPath, listPath])
        this.batchProcess = python

        let buffer = ''

        python.stdout.on('data', (data: Buffer) => {
          buffer += data.toString()
          const lines = buffer.split('\n')
          buffer = lines.pop() || '' // Keep incomplete line in buffer

          for (const line of lines) {
            if (!line.trim()) continue
            try {
              const result = JSON.parse(line)
              const imageId = imagePathMap.get(result.imagePath)
              if (imageId) {
                this.scores[imageId] = {
                  maxConfidence: result.maxConfidence,
                  avgConfidence: result.avgConfidence,
                  numPredictions: result.numPredictions
                }
              }
              this.batchProgress.processed++

              // Write scores every 10 images
              if (this.batchProgress.processed % 10 === 0) {
                this.writeScores().catch(err =>
                  logger.error(`Failed to write scores: ${err}`)
                )
              }
            } catch (err) {
              logger.error(`Failed to parse inference output: ${line}`)
            }
          }
        })

        python.stderr.on('data', (data: Buffer) => {
          const msg = data.toString().trim()
          if (msg) {
            // YOLO prints progress to stderr, only log errors
            if (msg.includes('Error') || msg.includes('Traceback')) {
              logger.error(`🤖 YOLO stderr: ${msg}`)
            }
          }
        })

        python.on('close', (code) => {
          // Process any remaining buffer
          if (buffer.trim()) {
            try {
              const result = JSON.parse(buffer)
              const imageId = imagePathMap.get(result.imagePath)
              if (imageId) {
                this.scores[imageId] = {
                  maxConfidence: result.maxConfidence,
                  avgConfidence: result.avgConfidence,
                  numPredictions: result.numPredictions
                }
                this.batchProgress.processed++
              }
            } catch { /* ignore */ }
          }

          this.batchProcess = null
          this.batchProgress.running = false

          // Final write
          this.writeScores().catch(err =>
            logger.error(`Failed to write final scores: ${err}`)
          )

          // Clean up temp file
          fs.unlink(listPath).catch(() => {})

          logger.info(`✅ Batch inference complete: ${this.batchProgress.processed}/${this.batchProgress.total} (exit code: ${code})`)
        })
      })
    }).catch(err => {
      logger.error(`Failed to start batch inference: ${err}`)
      this.batchProgress.running = false
    })
  }

  /**
   * Get the next prioritized image (lowest confidence first)
   */
  getNextPrioritizedImage(
    unannotatedImages: Array<{
      imageId: string
      imagePath: string
      faction: string
      source: 'reddit' | 'dakkadakka'
    }>,
    priorityFactions?: string[]
  ): {
    imageId: string
    imagePath: string
    faction: string
    source: 'reddit' | 'dakkadakka'
    confidenceScore?: number
  } | null {
    if (unannotatedImages.length === 0) return null

    // If no scores loaded, fall back to first image
    if (Object.keys(this.scores).length === 0) {
      return unannotatedImages[0]
    }

    // Score and sort images
    const scored = unannotatedImages.map(img => {
      const score = this.scores[img.imageId]
      let priority = score ? score.maxConfidence : 0.5 // Unknown images get medium priority

      // Boost priority for struggling factions (lower score = higher priority)
      if (priorityFactions && priorityFactions.includes(img.faction)) {
        priority *= 0.5 // Halve the confidence to push these up in priority
      }

      return { ...img, priority, confidenceScore: score?.maxConfidence }
    })

    // Sort by priority ascending (lowest confidence = highest priority)
    scored.sort((a, b) => a.priority - b.priority)

    const best = scored[0]
    return {
      imageId: best.imageId,
      imagePath: best.imagePath,
      faction: best.faction,
      source: best.source,
      confidenceScore: best.confidenceScore
    }
  }

  /**
   * Get current batch progress
   */
  getBatchProgress(): BatchProgress {
    return { ...this.batchProgress }
  }

  /**
   * Get total number of scored images
   */
  getTotalScored(): number {
    return Object.keys(this.scores).length
  }
}

export const activeLearningService = new ActiveLearningService()
