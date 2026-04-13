/**
 * OpenAI Provider
 *
 * OpenAI GPT-4 Vision implementation for bbox detection and classification.
 * Hardened with safe JSON parsing, response-shape checks, and timeouts.
 */

import OpenAI from 'openai'
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

export class OpenAIProvider extends AIProvider {
  constructor(apiKey, model) {
    super(apiKey, model)
    this.client = new OpenAI({ apiKey })
  }

  async detectBboxes(imageBuffer) {
    const base64Image = imageBuffer.toString('base64')
    const dataUrl = `data:image/jpeg;base64,${base64Image}`

    const call = this.client.chat.completions.create({
      model: this.model,
      messages: [
        {
          role: 'user',
          content: [
            { type: 'text', text: DETECTION_PROMPT },
            { type: 'image_url', image_url: { url: dataUrl } },
          ],
        },
      ],
      max_tokens: 4096,
    })

    const response = await withTimeout(call, TIMEOUT_MS, 'OpenAI detectBboxes')
    const text = extractTextContent(response, 'openai')
    const parsed = safeJsonParse(text, 'OpenAI detectBboxes')
    return normalizeDetections(parsed, 'OpenAI detectBboxes')
  }

  async classifyImage(cropBuffer, context = {}) {
    const base64Image = cropBuffer.toString('base64')
    const dataUrl = `data:image/jpeg;base64,${base64Image}`
    const prompt = buildClassifyPrompt(context)

    const call = this.client.chat.completions.create({
      model: this.model,
      messages: [
        {
          role: 'user',
          content: [
            { type: 'text', text: prompt },
            { type: 'image_url', image_url: { url: dataUrl } },
          ],
        },
      ],
      max_tokens: 2048,
    })

    const response = await withTimeout(call, TIMEOUT_MS, 'OpenAI classifyImage')
    const text = extractTextContent(response, 'openai')
    const parsed = safeJsonParse(text, 'OpenAI classifyImage')
    return normalizeClassification(parsed, 'OpenAI classifyImage')
  }
}
