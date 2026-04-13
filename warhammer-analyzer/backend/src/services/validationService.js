/**
 * Validation Service (PASS 3)
 *
 * Triangulation: Second opinion for low-confidence classifications.
 * CANNOT change the count - only validate/improve existing classifications.
 */

import { getValidationConfig, createProvider } from '../config/pipeline.js'
import { cropImage } from '../utils/imageProcessing.js'
import { logger } from '../utils/logger.js'

/**
 * Validate low-confidence classifications with second opinion
 *
 * @param {Buffer} imageBuffer - Full image as buffer
 * @param {Array} detections - Array of {id, bbox} from PASS 1
 * @param {Map} classifications - Map<id, classification> from PASS 2
 * @param {number} authorityCount - Immutable count from PASS 1
 * @returns {Promise<Object>} {validatedClassifications: Map, metadata}
 */
export async function validateClassifications(imageBuffer, detections, classifications, authorityCount) {
  const startTime = Date.now()
  const config = getValidationConfig()

  // Skip if triangulation disabled
  if (!config.enabled) {
    logger.info(`[PASS 3] Triangulation disabled, skipping validation`)
    return {
      validatedClassifications: classifications,
      metadata: {
        triangulationCount: 0,
        disagreementCount: 0,
        processingTimeMs: 0
      }
    }
  }

  logger.info(`[PASS 3] Starting validation (threshold: ${config.trigger_threshold})`)

  // Verify count integrity
  if (classifications.size !== authorityCount) {
    throw new Error(`Count integrity check failed: Expected ${authorityCount} classifications, got ${classifications.size}`)
  }

  const validator = await createProvider(config.provider, config.model)
  const validatedClassifications = new Map(classifications)

  let triangulationCount = 0
  let disagreementCount = 0

  for (const detection of detections) {
    const classification = classifications.get(detection.id)

    // Only validate low-confidence classifications
    if (classification.confidence >= config.trigger_threshold) {
      continue
    }

    logger.debug(`[PASS 3] Validating ${detection.id}: ${classification.unit} (confidence: ${classification.confidence})`)

    // Get second opinion
    const cropBuffer = await cropImage(imageBuffer, detection.bbox, 0.1)
    const secondOpinion = await validator.classifyImage(cropBuffer)

    triangulationCount++

    // Compare opinions
    if (secondOpinion.unit !== classification.unit) {
      disagreementCount++
      logger.warn(`[PASS 3] DISAGREEMENT on ${detection.id}: ${classification.unit} vs ${secondOpinion.unit}`)

      // Use higher confidence classification
      if (secondOpinion.confidence > classification.confidence) {
        logger.info(`[PASS 3] Using validator opinion (higher confidence)`)
        validatedClassifications.set(detection.id, {
          ...secondOpinion,
          tier: classification.tier,
          triangulated: true,
          disagreement: true,
          originalClassification: classification
        })
      } else {
        // Keep original but flag disagreement
        validatedClassifications.set(detection.id, {
          ...classification,
          triangulated: true,
          disagreement: true,
          validatorOpinion: secondOpinion
        })
      }
    } else {
      logger.debug(`[PASS 3] Agreement on ${detection.id}: ${classification.unit}`)
      validatedClassifications.set(detection.id, {
        ...classification,
        triangulated: true,
        disagreement: false
      })
    }
  }

  // CRITICAL: Final count integrity verification
  if (validatedClassifications.size !== authorityCount) {
    throw new Error(`Count integrity check failed: Expected ${authorityCount} validated classifications, got ${validatedClassifications.size}`)
  }

  const elapsed = Date.now() - startTime
  logger.info(`[PASS 3] ✓ Validated ${triangulationCount} classifications (${disagreementCount} disagreements, ${elapsed}ms)`)

  return {
    validatedClassifications,
    metadata: {
      triangulationCount,
      disagreementCount,
      processingTimeMs: elapsed
    }
  }
}
