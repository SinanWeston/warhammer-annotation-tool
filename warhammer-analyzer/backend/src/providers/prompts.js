/**
 * Shared prompt templates for every AI provider. Keep prompts in one
 * place so experiments (A/B copy, new context injection) don't require
 * editing four files in lockstep.
 */

export const DETECTION_PROMPT = `You are a Warhammer 40K miniature detection system.

TASK: Detect all Warhammer 40K miniatures in this image and return bounding boxes.

OUTPUT FORMAT (JSON only, no markdown):
{
  "detections": [
    { "bbox": [x_min, y_min, x_max, y_max], "confidence": 0.95 }
  ]
}

RULES:
- Bounding boxes must be in NORMALIZED coordinates [0.0-1.0]
- x_min, y_min = top-left corner
- x_max, y_max = bottom-right corner
- Include ALL miniatures, even if partially visible
- Each miniature gets ONE bbox
- confidence: 0.0-1.0 (how sure you are this is a miniature)

Return ONLY valid JSON, nothing else.`

const CLASSIFY_BASE = `You are a Warhammer 40K miniature identification expert.

TASK: Identify the unit type and faction of this miniature.

OUTPUT FORMAT (JSON only, no markdown):
{
  "unit": "unit_slug",
  "faction": "faction_slug",
  "confidence": 0.95,
  "reasoning": "Brief explanation of the visual cues you used"
}

RULES:
- unit: snake_case unit slug (e.g. "legionaries", "plague_marines", "termagants")
- faction: snake_case faction slug (e.g. "chaos_space_marines", "death_guard", "tyranids")
- confidence: 0.0-1.0 — be conservative; lower scores are fine when uncertain
- reasoning: 1-2 sentences naming the specific visual tells that drove the ID
- When unsure of the specific variant, pick the broader unit slug rather than guessing

Return ONLY valid JSON, nothing else.`

/**
 * Build a classification prompt. Optional context:
 *   - context.factionHint: narrow the faction decision ("chaos_space_marines")
 *   - context.allowedUnits: array of unit slugs the answer MUST come from
 *   - context.cheatsheet: free-form visual-cue reminders to tack on
 *
 * All context fields are optional. With no context, the prompt is
 * identical to the original single-provider version.
 */
export function buildClassifyPrompt(context = {}) {
  const extras = []

  if (typeof context.factionHint === 'string' && context.factionHint) {
    extras.push(
      `FACTION HINT: this miniature is from \`${context.factionHint}\`. ` +
        `Set "faction" to this value; only disagree if the image clearly shows a different faction.`
    )
  }

  if (Array.isArray(context.allowedUnits) && context.allowedUnits.length > 0) {
    const list = context.allowedUnits.map((s) => `  - ${s}`).join('\n')
    extras.push(
      `ALLOWED UNIT SLUGS (choose from this list; do not invent new slugs):\n${list}`
    )
  }

  if (typeof context.cheatsheet === 'string' && context.cheatsheet) {
    extras.push(`VISUAL CUES:\n${context.cheatsheet}`)
  }

  if (extras.length === 0) return CLASSIFY_BASE
  return `${CLASSIFY_BASE}\n\n${extras.join('\n\n')}`
}
