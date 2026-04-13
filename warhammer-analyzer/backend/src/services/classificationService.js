/**
 * Classification Service (PASS 2)
 *
 * Multi-tier cascade classification of detected miniatures.
 * CANNOT change the count - only classify existing detections.
 */

import { getClassificationConfig, createProvider } from '../config/pipeline.js'
import { cropImage } from '../utils/imageProcessing.js'
import { logger } from '../utils/logger.js'

/**
 * Classify all detected miniatures using multi-tier cascade
 *
 * @param {Buffer} imageBuffer - Full image as buffer
 * @param {Array} detections - Array of {id, bbox, confidence} from PASS 1
 * @param {number} authorityCount - Immutable count from PASS 1
 * @returns {Promise<Object>} {classifications: Map<id, classification>, metadata}
 */
export async function classifyMiniatures(imageBuffer, detections, authorityCount) {
  const startTime = Date.now()
  const config = getClassificationConfig()

  logger.info(`[PASS 2] Starting classification for ${detections.length} detections`)

  // Verify count integrity
  if (detections.length !== authorityCount) {
    throw new Error(`Count integrity check failed: Expected ${authorityCount}, got ${detections.length}`)
  }

  const classifications = new Map()
  const tierStats = { tier1: 0, tier2: 0, tier3: 0 }

  for (const detection of detections) {
    logger.debug(`[PASS 2] Classifying detection ${detection.id}`)

    // Crop image
    const cropBuffer = await cropImage(imageBuffer, detection.bbox, 0.1)

    // Multi-tier cascade
    let classification = null
    let usedTier = null

    for (const tier of config.tiers) {
      logger.debug(`[PASS 2] ${detection.id}: Trying ${tier.name}`)

      const classifier = await createProvider(tier.provider, tier.model)
      const result = await classifier.classifyImage(cropBuffer)

      logger.debug(`[PASS 2] ${detection.id}: ${tier.name} result: ${result.unit} (${result.confidence})`)

      // Check if confidence meets threshold
      if (result.confidence >= tier.confidence_threshold || !tier.escalate_on_low_confidence) {
        classification = {
          ...result,
          tier: tier.name
        }
        usedTier = tier.name
        tierStats[tier.name]++
        break
      }

      // Escalate to next tier
      logger.debug(`[PASS 2] ${detection.id}: Escalating from ${tier.name} (confidence ${result.confidence} < ${tier.confidence_threshold})`)
    }

    // Store classification linked to detection ID
    classifications.set(detection.id, classification)
  }

  // CRITICAL: Verify count integrity
  if (classifications.size !== authorityCount) {
    throw new Error(`Count integrity check failed: Expected ${authorityCount} classifications, got ${classifications.size}`)
  }

  const elapsed = Date.now() - startTime
  logger.info(`[PASS 2] ✓ Classified ${classifications.size} miniatures (${elapsed}ms)`)
  logger.info(`[PASS 2] Tier breakdown: T1=${tierStats.tier1}, T2=${tierStats.tier2}, T3=${tierStats.tier3}`)

  return {
    classifications,
    metadata: {
      totalCount: classifications.size,
      tierStats,
      processingTimeMs: elapsed
    }
  }
}
