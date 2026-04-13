/**
 * Claude AI Provider
 *
 * Anthropic Claude implementation for bbox detection and classification.
 * Hardened with safe JSON parsing, response-shape checks, and timeouts.
 */

import Anthropic from '@anthropic-ai/sdk'
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

export class ClaudeProvider extends AIProvider {
  constructor(apiKey, model) {
    super(apiKey, model)
    this.client = new Anthropic({ apiKey })
  }

  async detectBboxes(imageBuffer) {
    const base64Image = imageBuffer.toString('base64')
    const call = this.client.messages.create({
      model: this.model,
      max_tokens: 4096,
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'image',
              source: { type: 'base64', media_type: 'image/jpeg', data: base64Image },
            },
            { type: 'text', text: DETECTION_PROMPT },
          ],
        },
      ],
    })

    const response = await withTimeout(call, TIMEOUT_MS, 'Claude detectBboxes')
    const text = extractTextContent(response, 'claude')
    const parsed = safeJsonParse(text, 'Claude detectBboxes')
    return normalizeDetections(parsed, 'Claude detectBboxes')
  }

  async classifyImage(cropBuffer, context = {}) {
    const base64Image = cropBuffer.toString('base64')
    const prompt = buildClassifyPrompt(context)

    const call = this.client.messages.create({
      model: this.model,
      max_tokens: 2048,
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'image',
              source: { type: 'base64', media_type: 'image/jpeg', data: base64Image },
            },
            { type: 'text', text: prompt },
          ],
        },
      ],
    })

    const response = await withTimeout(call, TIMEOUT_MS, 'Claude classifyImage')
    const text = extractTextContent(response, 'claude')
    const parsed = safeJsonParse(text, 'Claude classifyImage')
    return normalizeClassification(parsed, 'Claude classifyImage')
  }
}
