/**
 * Image Processing Utilities
 *
 * Image manipulation using Sharp: cropping, resizing, format conversion
 */

import sharp from 'sharp'
import { denormalizeBbox, addPadding } from './bbox.js'

/**
 * Crop image using bbox coordinates
 *
 * @param {Buffer} imageBuffer - Input image as buffer
 * @param {Object} bbox - Normalized bbox {x1, y1, x2, y2} in [0-1]
 * @param {number} paddingRatio - Padding around bbox (default 0.1 = 10%)
 * @returns {Promise<Buffer>} Cropped image buffer
 */
export async function cropImage(imageBuffer, bbox, paddingRatio = 0.1) {
  // Get image metadata
  const metadata = await sharp(imageBuffer).metadata()
  const { width: imageWidth, height: imageHeight } = metadata

  // Add padding to bbox
  const paddedBbox = addPadding(bbox, paddingRatio)

  // Convert to pixel coordinates
  const pixelBbox = denormalizeBbox(paddedBbox, imageWidth, imageHeight)

  // Calculate crop dimensions
  const cropWidth = pixelBbox.x2 - pixelBbox.x1
  const cropHeight = pixelBbox.y2 - pixelBbox.y1

  // Perform crop
  const croppedBuffer = await sharp(imageBuffer)
    .extract({
      left: pixelBbox.x1,
      top: pixelBbox.y1,
      width: cropWidth,
      height: cropHeight
    })
    .jpeg({ quality: 90 })
    .toBuffer()

  return croppedBuffer
}

/**
 * Resize image to max dimensions while preserving aspect ratio
 *
 * @param {Buffer} imageBuffer - Input image
 * @param {number} maxWidth - Maximum width
 * @param {number} maxHeight - Maximum height
 * @returns {Promise<Buffer>} Resized image buffer
 */
export async function resizeImage(imageBuffer, maxWidth, maxHeight) {
  return await sharp(imageBuffer)
    .resize(maxWidth, maxHeight, {
      fit: 'inside',
      withoutEnlargement: true
    })
    .jpeg({ quality: 90 })
    .toBuffer()
}

/**
 * Get image dimensions
 *
 * @param {Buffer} imageBuffer - Input image
 * @returns {Promise<Object>} {width, height}
 */
export async function getImageDimensions(imageBuffer) {
  const metadata = await sharp(imageBuffer).metadata()
  return {
    width: metadata.width,
    height: metadata.height
  }
}

/**
 * Convert image to JPEG format
 *
 * @param {Buffer} imageBuffer - Input image (any format)
 * @param {number} quality - JPEG quality (1-100)
 * @returns {Promise<Buffer>} JPEG buffer
 */
export async function convertToJpeg(imageBuffer, quality = 90) {
  return await sharp(imageBuffer)
    .jpeg({ quality })
    .toBuffer()
}

/**
 * Crop multiple bboxes from the same image (batch operation)
 *
 * @param {Buffer} imageBuffer - Input image
 * @param {Array} bboxes - Array of {id, bbox} objects
 * @param {number} paddingRatio - Padding around bboxes
 * @returns {Promise<Array>} Array of {id, cropBuffer}
 */
export async function cropMultiple(imageBuffer, bboxes, paddingRatio = 0.1) {
  const crops = []

  for (const { id, bbox } of bboxes) {
    const cropBuffer = await cropImage(imageBuffer, bbox, paddingRatio)
    crops.push({ id, cropBuffer })
  }

  return crops
}
