/**
 * Gemini Provider
 *
 * Google Gemini implementation for bbox detection and classification.
 * Hardened with safe JSON parsing, response-shape checks, and timeouts.
 */

import { GoogleGenerativeAI } from '@google/generative-ai'
import { AIProvider } from './base.js'
import {
  safeJsonParse,
  extractTextContent,
  withTimeout,
  normalizeDetections,
  normalizeClassification,
} from './utils.js'
import { DETECTION_PROMPT, buildClassifyPrompt } from './prompts.js'

const TIMEOUT_MS = 30_000

export class GeminiProvider extends AIProvider {
  constructor(apiKey, model) {
    super(apiKey, model)
    this.client = new GoogleGenerativeAI(apiKey)
  }

  async detectBboxes(imageBuffer) {
    const base64Image = imageBuffer.toString('base64')
    const model = this.client.getGenerativeModel({ model: this.model })

    const call = model
      .generateContent([
        DETECTION_PROMPT,
        { inlineData: { mimeType: 'image/jpeg', data: base64Image } },
      ])
      .then((result) => result.response)

    const response = await withTimeout(call, TIMEOUT_MS, 'Gemini detectBboxes')
    const text = extractTextContent(response, 'gemini')
    const parsed = safeJsonParse(text, 'Gemini detectBboxes')
    return normalizeDetections(parsed, 'Gemini detectBboxes')
  }

  async classifyImage(cropBuffer, context = {}) {
    const base64Image = cropBuffer.toString('base64')
    const model = this.client.getGenerativeModel({ model: this.model })
    const prompt = buildClassifyPrompt(context)

    const call = model
      .generateContent([
        prompt,
        { inlineData: { mimeType: 'image/jpeg', data: base64Image } },
      ])
      .then((result) => result.response)

    const response = await withTimeout(call, TIMEOUT_MS, 'Gemini classifyImage')
    const text = extractTextContent(response, 'gemini')
    const parsed = safeJsonParse(text, 'Gemini classifyImage')
    return normalizeClassification(parsed, 'Gemini classifyImage')
  }
}
