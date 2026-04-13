/**
 * Bounding Box Utilities
 *
 * Provides bbox operations: IoU, NMS, UUID assignment, normalization
 */

import { randomUUID } from 'crypto'

/**
 * Calculate Intersection over Union (IoU) between two bboxes
 * @param {Object} bbox1 - {x1, y1, x2, y2}
 * @param {Object} bbox2 - {x1, y1, x2, y2}
 * @returns {number} IoU score (0.0-1.0)
 */
export function calculateIoU(bbox1, bbox2) {
  // Calculate intersection
  const x1 = Math.max(bbox1.x1, bbox2.x1)
  const y1 = Math.max(bbox1.y1, bbox2.y1)
  const x2 = Math.min(bbox1.x2, bbox2.x2)
  const y2 = Math.min(bbox1.y2, bbox2.y2)

  const intersectionWidth = Math.max(0, x2 - x1)
  const intersectionHeight = Math.max(0, y2 - y1)
  const intersectionArea = intersectionWidth * intersectionHeight

  // Calculate union
  const bbox1Area = (bbox1.x2 - bbox1.x1) * (bbox1.y2 - bbox1.y1)
  const bbox2Area = (bbox2.x2 - bbox2.x1) * (bbox2.y2 - bbox2.y1)
  const unionArea = bbox1Area + bbox2Area - intersectionArea

  // Return IoU
  return unionArea === 0 ? 0 : intersectionArea / unionArea
}

/**
 * Non-Maximum Suppression (NMS)
 * Removes duplicate/overlapping bboxes, keeping only the highest confidence
 *
 * @param {Array} detections - Array of {bbox: {x1,y1,x2,y2}, confidence}
 * @param {number} iouThreshold - IoU threshold for considering bboxes as duplicates
 * @returns {Array} Filtered detections
 */
export function applyNMS(detections, iouThreshold = 0.5) {
  if (detections.length === 0) return []

  // Sort by confidence (descending)
  const sorted = [...detections].sort((a, b) => b.confidence - a.confidence)

  const keep = []
  const suppressed = new Set()

  for (let i = 0; i < sorted.length; i++) {
    if (suppressed.has(i)) continue

    keep.push(sorted[i])

    // Suppress all boxes with high IoU with this one
    for (let j = i + 1; j < sorted.length; j++) {
      if (suppressed.has(j)) continue

      const iou = calculateIoU(sorted[i].bbox, sorted[j].bbox)
      if (iou >= iouThreshold) {
        suppressed.add(j)
      }
    }
  }

  return keep
}

/**
 * Assign stable UUIDs to detections
 * This establishes the count-index lock
 *
 * @param {Array} detections - Array of {bbox, confidence}
 * @returns {Array} Detections with id field added
 */
export function assignStableIds(detections) {
  return detections.map(detection => ({
    ...detection,
    id: randomUUID()
  }))
}

/**
 * Normalize bbox coordinates to [0.0-1.0] range
 * @param {Object} bbox - {x1, y1, x2, y2} in pixels
 * @param {number} imageWidth - Image width in pixels
 * @param {number} imageHeight - Image height in pixels
 * @returns {Object} Normalized bbox
 */
export function normalizeBbox(bbox, imageWidth, imageHeight) {
  return {
    x1: bbox.x1 / imageWidth,
    y1: bbox.y1 / imageHeight,
    x2: bbox.x2 / imageWidth,
    y2: bbox.y2 / imageHeight
  }
}

/**
 * Denormalize bbox coordinates from [0.0-1.0] to pixel coordinates
 * @param {Object} bbox - {x1, y1, x2, y2} normalized
 * @param {number} imageWidth - Image width in pixels
 * @param {number} imageHeight - Image height in pixels
 * @returns {Object} Pixel bbox
 */
export function denormalizeBbox(bbox, imageWidth, imageHeight) {
  return {
    x1: Math.round(bbox.x1 * imageWidth),
    y1: Math.round(bbox.y1 * imageHeight),
    x2: Math.round(bbox.x2 * imageWidth),
    y2: Math.round(bbox.y2 * imageHeight)
  }
}

/**
 * Calculate bbox area
 * @param {Object} bbox - {x1, y1, x2, y2}
 * @returns {number} Area
 */
export function calculateArea(bbox) {
  return (bbox.x2 - bbox.x1) * (bbox.y2 - bbox.y1)
}

/**
 * Validate bbox coordinates
 * @param {Object} bbox - {x1, y1, x2, y2}
 * @returns {boolean} True if valid
 */
export function isValidBbox(bbox) {
  return (
    bbox.x1 >= 0 &&
    bbox.y1 >= 0 &&
    bbox.x2 > bbox.x1 &&
    bbox.y2 > bbox.y1 &&
    bbox.x1 <= 1 &&
    bbox.y1 <= 1 &&
    bbox.x2 <= 1 &&
    bbox.y2 <= 1
  )
}

/**
 * Add padding to bbox (useful for cropping with context)
 * @param {Object} bbox - {x1, y1, x2, y2} normalized [0-1]
 * @param {number} paddingRatio - Padding as ratio of bbox size (e.g., 0.1 = 10%)
 * @returns {Object} Padded bbox (clamped to [0-1])
 */
export function addPadding(bbox, paddingRatio = 0.1) {
  const width = bbox.x2 - bbox.x1
  const height = bbox.y2 - bbox.y1

  const xPadding = width * paddingRatio
  const yPadding = height * paddingRatio

  return {
    x1: Math.max(0, bbox.x1 - xPadding),
    y1: Math.max(0, bbox.y1 - yPadding),
    x2: Math.min(1, bbox.x2 + xPadding),
    y2: Math.min(1, bbox.y2 + yPadding)
  }
}
