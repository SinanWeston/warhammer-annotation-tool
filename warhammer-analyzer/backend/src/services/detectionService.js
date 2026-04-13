/**
 * Detection Service (PASS 1)
 *
 * Establishes count authority through bbox detection.
 * The count determined here is IMMUTABLE.
 */

import { getDetectionConfig, createProvider } from '../config/pipeline.js'
import { applyNMS, assignStableIds, isValidBbox } from '../utils/bbox.js'
import { logger } from '../utils/logger.js'

/**
 * Detect miniatures in image and establish count authority
 *
 * @param {Buffer} imageBuffer - Full image as buffer
 * @returns {Promise<Object>} {detections: Array, authorityCount: number}
 */
export async function detectMiniatures(imageBuffer) {
  const startTime = Date.now()
  const config = getDetectionConfig()

  logger.info(`[PASS 1] Starting detection with ${config.provider}/${config.model}`)

  // Create detection provider
  const detector = await createProvider(config.provider, config.model)

  // Run detection
  const rawDetections = await detector.detectBboxes(imageBuffer)
  logger.info(`[PASS 1] Detected ${rawDetections.length} raw bboxes`)

  // Filter out invalid bboxes
  const validDetections = rawDetections.filter(d => {
    const valid = isValidBbox(d.bbox) && d.confidence >= config.confidence_threshold
    if (!valid) {
      logger.warn(`[PASS 1] Filtered out invalid bbox:`, d.bbox)
    }
    return valid
  })

  logger.info(`[PASS 1] ${validDetections.length} valid bboxes after filtering`)

  // Apply Non-Maximum Suppression to remove duplicates
  const nmsDetections = applyNMS(validDetections, config.nms_iou_threshold)
  logger.info(`[PASS 1] ${nmsDetections.length} bboxes after NMS (removed ${validDetections.length - nmsDetections.length} duplicates)`)

  // Assign stable UUIDs (COUNT LOCK ESTABLISHED)
  const detectionsWithIds = assignStableIds(nmsDetections)
  const authorityCount = detectionsWithIds.length

  const elapsed = Date.now() - startTime
  logger.info(`[PASS 1] ✓ Count authority established: ${authorityCount} miniatures (${elapsed}ms)`)

  return {
    detections: detectionsWithIds,
    authorityCount,
    metadata: {
      provider: config.provider,
      model: config.model,
      rawCount: rawDetections.length,
      validCount: validDetections.length,
      nmsCount: nmsDetections.length,
      finalCount: authorityCount,
      processingTimeMs: elapsed
    }
  }
}
