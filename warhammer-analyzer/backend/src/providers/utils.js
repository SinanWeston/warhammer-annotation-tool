/**
 * Shared provider utilities — safe JSON parsing, response shape validation,
 * and async timeouts. Every provider should use these rather than parsing
 * LLM responses by hand.
 */

/**
 * Parse a JSON object out of an arbitrary LLM response string. LLMs
 * routinely ignore "return only JSON" instructions and wrap the payload
 * in markdown code fences, explanatory text, or both.
 *
 * Strategy (most-specific first):
 *   1. Strip ``` or ```json code fences.
 *   2. Try JSON.parse on the stripped text as-is.
 *   3. Fall back to the widest {...} or [...] substring.
 *   4. Throw a descriptive error that includes a truncated preview.
 *
 * @param {string} text
 * @param {string} [label] — included in error messages, e.g. "Claude detect"
 * @returns {object}
 */
export function safeJsonParse(text, label = 'LLM response') {
  if (typeof text !== 'string' || text.length === 0) {
    throw new Error(`${label} returned empty text`)
  }

  // Strip markdown fences: ```json ... ``` or ``` ... ```
  let cleaned = text.trim()
  const fenceMatch = cleaned.match(/^```(?:json)?\s*\n?([\s\S]*?)\n?\s*```$/i)
  if (fenceMatch) cleaned = fenceMatch[1].trim()

  // Direct parse.
  try {
    return JSON.parse(cleaned)
  } catch {
    // fall through
  }

  // Widest object/array extraction. Prefers objects, then arrays.
  const objMatch = cleaned.match(/\{[\s\S]*\}/)
  const arrMatch = cleaned.match(/\[[\s\S]*\]/)
  for (const candidate of [objMatch?.[0], arrMatch?.[0]].filter(Boolean)) {
    try {
      return JSON.parse(candidate)
    } catch {
      // try next
    }
  }

  const preview = text.length > 240 ? text.slice(0, 240) + '…' : text
  throw new Error(`${label} did not return parseable JSON. Preview: ${JSON.stringify(preview)}`)
}

/**
 * Extract the first text content from a provider response safely. Each
 * provider SDK uses a slightly different shape — each call here maps
 * the provider's field path, checks for the usual emptiness cases, and
 * throws a consistent descriptive error when the response is malformed.
 *
 * Supported kinds: 'claude' | 'openai' | 'gemini' | 'openrouter'
 */
export function extractTextContent(response, kind) {
  switch (kind) {
    case 'claude': {
      const content = response?.content
      if (!Array.isArray(content) || content.length === 0) {
        throw new Error('Claude response.content is missing or empty')
      }
      const textBlock = content.find((b) => b?.type === 'text' && typeof b.text === 'string')
      if (!textBlock) throw new Error('Claude response has no text block')
      return textBlock.text
    }
    case 'openai':
    case 'openrouter': {
      const choices = response?.choices
      if (!Array.isArray(choices) || choices.length === 0) {
        throw new Error(`${kind} response.choices is missing or empty`)
      }
      const text = choices[0]?.message?.content
      if (typeof text !== 'string' || text.length === 0) {
        throw new Error(`${kind} response.choices[0].message.content is missing or empty`)
      }
      return text
    }
    case 'gemini': {
      // The @google/generative-ai SDK returns a GenerateContentResponse;
      // call .text() to extract the primary text.
      if (typeof response?.text === 'function') return response.text()
      // Fallback for @google/genai (different shape).
      const cand = response?.candidates?.[0]
      const text = cand?.content?.parts?.find?.((p) => typeof p?.text === 'string')?.text
      if (typeof text !== 'string' || text.length === 0) {
        throw new Error('Gemini response has no text content')
      }
      return text
    }
    default:
      throw new Error(`Unknown provider kind: ${kind}`)
  }
}

/**
 * Wrap a promise with a hard deadline. Rejects with a TimeoutError if the
 * promise doesn't settle in time. Use for every LLM API call so a stuck
 * request can't block the Express handler indefinitely.
 *
 * @template T
 * @param {Promise<T>} promise
 * @param {number} ms — default 30_000
 * @param {string} [label]
 * @returns {Promise<T>}
 */
export function withTimeout(promise, ms = 30_000, label = 'operation') {
  let timeoutId
  const timeout = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      const err = new Error(`${label} timed out after ${ms}ms`)
      err.code = 'TIMEOUT'
      reject(err)
    }, ms)
  })
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timeoutId))
}

/**
 * Validate a bbox detections array shape and coerce to the standard
 * normalized-coordinate format the downstream pipeline expects.
 */
export function normalizeDetections(raw, label = 'detections') {
  if (!raw || typeof raw !== 'object') {
    throw new Error(`${label} parse: expected object, got ${typeof raw}`)
  }
  const list = Array.isArray(raw) ? raw : raw.detections
  if (!Array.isArray(list)) {
    throw new Error(`${label} parse: no detections[] array in response`)
  }
  return list
    .map((d, i) => {
      const bbox = Array.isArray(d?.bbox) ? d.bbox : null
      if (!bbox || bbox.length < 4) return null
      const conf = typeof d.confidence === 'number' ? d.confidence : 0.5
      return {
        bbox: { x1: Number(bbox[0]), y1: Number(bbox[1]), x2: Number(bbox[2]), y2: Number(bbox[3]) },
        confidence: Math.min(1, Math.max(0, conf)),
        _idx: i,
      }
    })
    .filter(Boolean)
    .filter((d) =>
      [d.bbox.x1, d.bbox.y1, d.bbox.x2, d.bbox.y2].every((v) => Number.isFinite(v))
    )
}

/**
 * Validate a classification result shape.
 */
export function normalizeClassification(raw, label = 'classification') {
  if (!raw || typeof raw !== 'object') {
    throw new Error(`${label} parse: expected object, got ${typeof raw}`)
  }
  const unit = typeof raw.unit === 'string' ? raw.unit : 'Unknown'
  const faction = typeof raw.faction === 'string' ? raw.faction : 'Unknown'
  const confidence =
    typeof raw.confidence === 'number' ? Math.min(1, Math.max(0, raw.confidence)) : 0
  const reasoning = typeof raw.reasoning === 'string' ? raw.reasoning : ''
  return { unit, faction, confidence, reasoning }
}
