/**
 * Dashboard Stats Service
 *
 * Reads all annotation JSONs, computes aggregate stats, caches in memory (60s TTL).
 * Cache is invalidated when an annotation is saved.
 */

import fs from 'fs/promises'
import path from 'path'
import logger from '../utils/logger'

interface BoxSizeStats {
  avgWidth: number
  avgHeight: number
  avgAreaRatio: number
}

interface OutlierEntry {
  imageId: string
  faction: string
  reason: 'tiny_box' | 'huge_box' | 'too_many_boxes'
  details: string
  boxCount?: number
  areaRatio?: number
}

export interface DashboardStats {
  boxesPerImage: {
    min: number
    max: number
    avg: number
    median: number
    distribution: Record<string, number>
  }
  boxSizesByFaction: Record<string, BoxSizeStats>
  annotationSpeed: {
    perDay: Record<string, number>
  }
  outliers: OutlierEntry[]
  totalAnnotations: number
  totalBoxes: number
}

class DashboardStatsService {
  private annotationsPath: string
  private cache: DashboardStats | null = null
  private cacheTimestamp: number = 0
  private cacheTTL: number = 60_000 // 60 seconds

  constructor() {
    this.annotationsPath = path.join(__dirname, '../../training_data_annotations')
  }

  /**
   * Invalidate the cache (called after saving an annotation)
   */
  invalidateCache(): void {
    this.cache = null
    this.cacheTimestamp = 0
  }

  /**
   * Get dashboard stats, using cache if fresh
   */
  async getStats(): Promise<DashboardStats> {
    const now = Date.now()
    if (this.cache && (now - this.cacheTimestamp) < this.cacheTTL) {
      return this.cache
    }

    const stats = await this.computeStats()
    this.cache = stats
    this.cacheTimestamp = Date.now()
    return stats
  }

  /**
   * Read all annotation JSONs and compute stats
   */
  private async computeStats(): Promise<DashboardStats> {
    const startTime = Date.now()

    let files: string[]
    try {
      files = await fs.readdir(this.annotationsPath)
      files = files.filter(f => f.endsWith('.json'))
    } catch {
      // No annotations directory yet
      return this.emptyStats()
    }

    if (files.length === 0) return this.emptyStats()

    // Read all annotations with concurrency limit
    const CONCURRENCY = 50
    const annotations: any[] = []

    for (let i = 0; i < files.length; i += CONCURRENCY) {
      const batch = files.slice(i, i + CONCURRENCY)
      const results = await Promise.all(
        batch.map(async (file) => {
          try {
            const data = await fs.readFile(path.join(this.annotationsPath, file), 'utf-8')
            return JSON.parse(data)
          } catch {
            return null
          }
        })
      )
      annotations.push(...results.filter(Boolean))
    }

    // Compute stats
    const boxCounts: number[] = []
    const factionBoxSizes: Record<string, { widths: number[]; heights: number[]; areaRatios: number[] }> = {}
    const speedByDay: Record<string, number> = {}
    const outliers: OutlierEntry[] = []
    let totalBoxes = 0

    for (const ann of annotations) {
      const numBoxes = ann.annotations?.length || 0
      boxCounts.push(numBoxes)
      totalBoxes += numBoxes

      // Annotation speed (by day)
      if (ann.annotatedAt) {
        const day = ann.annotatedAt.substring(0, 10) // YYYY-MM-DD
        speedByDay[day] = (speedByDay[day] || 0) + 1
      }

      const imgWidth = ann.width || 1
      const imgHeight = ann.height || 1
      const imgArea = imgWidth * imgHeight

      // Too many boxes outlier
      if (numBoxes >= 20) {
        outliers.push({
          imageId: ann.imageId,
          faction: ann.faction || 'unknown',
          reason: 'too_many_boxes',
          details: `${numBoxes} boxes in one image`,
          boxCount: numBoxes
        })
      }

      for (const box of (ann.annotations || [])) {
        const model = box.modelBbox
        if (!model) continue

        const faction = ann.faction || 'unknown'

        if (!factionBoxSizes[faction]) {
          factionBoxSizes[faction] = { widths: [], heights: [], areaRatios: [] }
        }

        const boxArea = model.width * model.height
        const areaRatio = boxArea / imgArea

        factionBoxSizes[faction].widths.push(model.width / imgWidth)
        factionBoxSizes[faction].heights.push(model.height / imgHeight)
        factionBoxSizes[faction].areaRatios.push(areaRatio)

        // Tiny box outlier (<1% of image area)
        if (areaRatio < 0.01) {
          outliers.push({
            imageId: ann.imageId,
            faction,
            reason: 'tiny_box',
            details: `Box area is ${(areaRatio * 100).toFixed(2)}% of image`,
            areaRatio
          })
        }

        // Huge box outlier (>90% of image area)
        if (areaRatio > 0.9) {
          outliers.push({
            imageId: ann.imageId,
            faction,
            reason: 'huge_box',
            details: `Box area is ${(areaRatio * 100).toFixed(1)}% of image`,
            areaRatio
          })
        }
      }
    }

    // Box counts stats
    const sorted = [...boxCounts].sort((a, b) => a - b)
    const median = sorted.length > 0
      ? sorted.length % 2 === 0
        ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
        : sorted[Math.floor(sorted.length / 2)]
      : 0

    // Distribution buckets: 0, 1, 2, 3, 4, 5, 6-10, 11-20, 20+
    const distribution: Record<string, number> = {}
    for (const count of boxCounts) {
      let bucket: string
      if (count <= 5) bucket = String(count)
      else if (count <= 10) bucket = '6-10'
      else if (count <= 20) bucket = '11-20'
      else bucket = '20+'
      distribution[bucket] = (distribution[bucket] || 0) + 1
    }

    // Faction box sizes
    const boxSizesByFaction: Record<string, BoxSizeStats> = {}
    for (const [faction, data] of Object.entries(factionBoxSizes)) {
      const avg = (arr: number[]) => arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : 0
      boxSizesByFaction[faction] = {
        avgWidth: avg(data.widths),
        avgHeight: avg(data.heights),
        avgAreaRatio: avg(data.areaRatios)
      }
    }

    const elapsed = Date.now() - startTime
    logger.info(`📊 Dashboard stats computed in ${elapsed}ms (${annotations.length} annotations, ${totalBoxes} boxes)`)

    return {
      boxesPerImage: {
        min: sorted.length > 0 ? sorted[0] : 0,
        max: sorted.length > 0 ? sorted[sorted.length - 1] : 0,
        avg: boxCounts.length > 0 ? totalBoxes / boxCounts.length : 0,
        median,
        distribution
      },
      boxSizesByFaction,
      annotationSpeed: { perDay: speedByDay },
      outliers,
      totalAnnotations: annotations.length,
      totalBoxes
    }
  }

  private emptyStats(): DashboardStats {
    return {
      boxesPerImage: { min: 0, max: 0, avg: 0, median: 0, distribution: {} },
      boxSizesByFaction: {},
      annotationSpeed: { perDay: {} },
      outliers: [],
      totalAnnotations: 0,
      totalBoxes: 0
    }
  }
}

export const dashboardStatsService = new DashboardStatsService()
