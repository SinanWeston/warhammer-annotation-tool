/**
 * LLaMA Provider (OpenRouter)
 *
 * Meta LLaMA + any OpenRouter-hosted vision model. Hardened with safe
 * JSON parsing, response-shape checks, and fetch timeouts via AbortSignal.
 */

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
const OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'

export class LLaMAProvider extends AIProvider {
  constructor(apiKey, model) {
    super(apiKey, model)
  }

  async _call(prompt, imageBuffer, label, { maxTokens = 2048 } = {}) {
    const dataUrl = `data:image/jpeg;base64,${imageBuffer.toString('base64')}`

    const controller = new AbortController()
    const doFetch = fetch(OPENROUTER_URL, {
      method: 'POST',
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': 'https://warhammer-analyzer.local',
        'X-Title': 'Warhammer Analyzer',
      },
      body: JSON.stringify({
        model: this.model,
        max_tokens: maxTokens,
        messages: [
          {
            role: 'user',
            content: [
              { type: 'text', text: prompt },
              { type: 'image_url', image_url: { url: dataUrl } },
            ],
          },
        ],
      }),
    })

    let response
    try {
      response = await withTimeout(doFetch, TIMEOUT_MS, label)
    } catch (err) {
      controller.abort()
      throw err
    }

    if (!response.ok) {
      const body = await response.text().catch(() => '(no body)')
      throw new Error(`${label}: OpenRouter ${response.status} ${body}`)
    }
    const json = await response.json()
    return extractTextContent(json, 'openrouter')
  }

  async detectBboxes(imageBuffer) {
    const text = await this._call(DETECTION_PROMPT, imageBuffer, 'LLaMA detectBboxes', { maxTokens: 4096 })
    const parsed = safeJsonParse(text, 'LLaMA detectBboxes')
    return normalizeDetections(parsed, 'LLaMA detectBboxes')
  }

  async classifyImage(cropBuffer, context = {}) {
    const prompt = buildClassifyPrompt(context)
    const text = await this._call(prompt, cropBuffer, 'LLaMA classifyImage', { maxTokens: 2048 })
    const parsed = safeJsonParse(text, 'LLaMA classifyImage')
    return normalizeClassification(parsed, 'LLaMA classifyImage')
  }
}
