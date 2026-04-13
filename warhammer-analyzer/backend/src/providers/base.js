/**
 * Base AI Provider
 * 
 * Abstract base class for all AI providers.
 * Implement this interface to add new providers.
 */

export class AIProvider {
  constructor(apiKey, model) {
    this.apiKey = apiKey
    this.model = model
  }

  /**
   * Detect bounding boxes in an image
   * @param {Buffer} imageBuffer - Image as buffer
   * @returns {Promise<Array>} Array of {bbox: {x1, y1, x2, y2}, confidence}
   */
  async detectBboxes(imageBuffer) {
    throw new Error('detectBboxes() must be implemented by provider')
  }

  /**
   * Classify a cropped image
   * @param {Buffer} cropBuffer - Cropped image as buffer
   * @param {Object} context - Additional context (original image, other detections, etc.)
   * @returns {Promise<Object>} {unit, faction, confidence}
   */
  async classifyImage(cropBuffer, context = {}) {
    throw new Error('classifyImage() must be implemented by provider')
  }

  /**
   * Analyze full image (detection + classification in one call)
   * @param {Buffer} imageBuffer - Full image as buffer
   * @returns {Promise<Array>} Array of {bbox, unit, faction, confidence}
   */
  async analyzeImage(imageBuffer) {
    throw new Error('analyzeImage() can be optionally implemented for single-pass providers')
  }

  /**
   * Convert buffer to base64 data URL
   */
  bufferToBase64(buffer, mimeType = 'image/jpeg') {
    const base64 = buffer.toString('base64')
    return `data:${mimeType};base64,${base64}`
  }
}
