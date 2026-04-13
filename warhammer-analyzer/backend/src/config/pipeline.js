/**
 * Pipeline Configuration
 *
 * Modular configuration for the three-pass analysis pipeline and the
 * labelling mode. Every provider, model, and threshold is configurable
 * via environment variables with sensible defaults.
 *
 * Providers:
 *   claude     — Anthropic SDK, needs ANTHROPIC_API_KEY
 *   openai     — OpenAI SDK, needs OPENAI_API_KEY
 *   gemini     — Google Gen AI SDK, needs GOOGLE_API_KEY
 *   openrouter — OpenRouter REST, needs OPENROUTER_API_KEY. Works for ANY
 *                model OpenRouter hosts (claude/gpt/gemini/llama/etc.).
 *   llama      — alias of openrouter (kept for backward compat)
 */

const VALID_PROVIDERS = new Set(['claude', 'openai', 'gemini', 'openrouter', 'llama', 'anthropic'])

export const PIPELINE_CONFIG = {
  detection: {
    provider: process.env.DETECTION_PROVIDER || 'openrouter',
    model: process.env.DETECTION_MODEL || 'anthropic/claude-haiku-4-5',
    confidence_threshold: parseFloat(process.env.DETECTION_CONFIDENCE || '0.5'),
    nms_iou_threshold: parseFloat(process.env.NMS_IOU_THRESHOLD || '0.5'),
    padding: parseFloat(process.env.BBOX_PADDING || '0.1'),
  },

  classification: {
    enabled: process.env.ENABLE_MULTI_TIER !== 'false',
    tiers: [
      {
        name: 'tier1',
        provider: process.env.TIER1_PROVIDER || 'openrouter',
        model: process.env.TIER1_MODEL || 'google/gemini-2.5-flash-lite',
        confidence_threshold: parseFloat(process.env.TIER1_THRESHOLD || '0.85'),
        escalate_on_low_confidence: true,
      },
      {
        name: 'tier2',
        provider: process.env.TIER2_PROVIDER || 'openrouter',
        model: process.env.TIER2_MODEL || 'anthropic/claude-sonnet-4.5',
        confidence_threshold: parseFloat(process.env.TIER2_THRESHOLD || '0.75'),
        escalate_on_low_confidence: true,
      },
      {
        name: 'tier3',
        provider: process.env.TIER3_PROVIDER || 'openrouter',
        model: process.env.TIER3_MODEL || 'openai/gpt-4o',
        confidence_threshold: 0,
        escalate_on_low_confidence: false,
      },
    ],
  },

  validation: {
    enabled: process.env.ENABLE_TRIANGULATION !== 'false',
    provider: process.env.VALIDATION_PROVIDER || 'openrouter',
    model: process.env.VALIDATION_MODEL || 'meta-llama/llama-3.2-90b-vision-instruct',
    trigger_threshold: parseFloat(process.env.TRIANGULATION_THRESHOLD || '0.75'),
  },

  // Labelling-mode config — drives the new crop-labelling endpoints.
  // Paths resolve relative to the monorepo root (warhammer-analyzer/..).
  labelling: {
    enabled: process.env.LABELLING_ENABLED !== 'false',
    cropsDir:
      process.env.LABELLING_CROPS_DIR ||
      '../scripts/phase1/crops',
    labelsCsv:
      process.env.LABELLING_LABELS_CSV ||
      '../scripts/phase1/labels.csv',
    cheatsheet:
      process.env.LABELLING_CHEATSHEET ||
      '../scripts/phase1/unit_slugs_cheatsheet.md',
    suggestProvider: process.env.LABELLING_SUGGEST_PROVIDER || 'openrouter',
    suggestModel: process.env.LABELLING_SUGGEST_MODEL || 'anthropic/claude-sonnet-4.5',
  },

  clip: {
    enabled: process.env.ENABLE_CLIP === 'true',
    disagreement_threshold: parseFloat(process.env.CLIP_DISAGREEMENT_THRESHOLD || '0.80'),
    service_url: process.env.CLIP_SERVICE_URL || 'http://localhost:8000',
  },

  count_lock: { enabled: true, verify_integrity: true },

  api_keys: {
    openrouter: process.env.OPENROUTER_API_KEY,
    anthropic: process.env.ANTHROPIC_API_KEY,
    openai: process.env.OPENAI_API_KEY,
    google: process.env.GOOGLE_API_KEY,
  },

  server: {
    port: parseInt(process.env.PORT || '3002', 10),
    frontendPort: parseInt(process.env.FRONTEND_PORT || '3003', 10),
    maxUploadBytes: parseInt(process.env.MAX_UPLOAD_BYTES || String(50 * 1024 * 1024), 10),
    logLevel: process.env.LOG_LEVEL || 'info',
  },
}

export const getDetectionConfig = () => PIPELINE_CONFIG.detection
export const getClassificationConfig = () => PIPELINE_CONFIG.classification
export const getValidationConfig = () => PIPELINE_CONFIG.validation
export const getLabellingConfig = () => PIPELINE_CONFIG.labelling
export const getServerConfig = () => PIPELINE_CONFIG.server
export const isClipEnabled = () => PIPELINE_CONFIG.clip.enabled

/**
 * Return the API key appropriate for a provider, preferring the native
 * key and falling back to OpenRouter. Returns undefined if no key works.
 */
export function getApiKey(provider) {
  const { anthropic, openai, google, openrouter } = PIPELINE_CONFIG.api_keys
  switch (provider) {
    case 'claude':
    case 'anthropic':
      return anthropic || undefined
    case 'openai':
      return openai || undefined
    case 'gemini':
      return google || undefined
    case 'openrouter':
    case 'llama':
      return openrouter || undefined
    default:
      return undefined
  }
}

/**
 * Resolve a provider name to the actual provider kind we can instantiate.
 * If someone asks for 'claude' but only OPENROUTER_API_KEY is configured,
 * we silently upgrade to 'openrouter' with an appropriately-prefixed model
 * so the request still succeeds via OpenRouter's Anthropic-compatible route.
 */
export function resolveProvider(providerName, model) {
  if (!VALID_PROVIDERS.has(providerName)) {
    throw new Error(
      `Unknown provider: ${providerName}. ` +
        `Valid providers: ${[...VALID_PROVIDERS].join(', ')}`
    )
  }

  const nativeKey = getApiKey(providerName)
  if (nativeKey) return { kind: providerName, apiKey: nativeKey, model }

  // Fallback to OpenRouter, rewriting the model to OpenRouter's canonical
  // prefix when we can infer it from the original provider name.
  const openrouterKey = PIPELINE_CONFIG.api_keys.openrouter
  if (!openrouterKey) {
    throw new Error(
      `No API key available for provider "${providerName}" and no ` +
        `OPENROUTER_API_KEY fallback. Set one of: ANTHROPIC_API_KEY, ` +
        `OPENAI_API_KEY, GOOGLE_API_KEY, OPENROUTER_API_KEY.`
    )
  }

  let fallbackModel = model
  if (!model.includes('/')) {
    switch (providerName) {
      case 'claude':
      case 'anthropic':
        fallbackModel = `anthropic/${model}`
        break
      case 'openai':
        fallbackModel = `openai/${model}`
        break
      case 'gemini':
        fallbackModel = `google/${model}`
        break
      case 'llama':
        // Leave alone; OpenRouter model ids for Llama are already fully-qualified.
        break
    }
  }
  return { kind: 'openrouter', apiKey: openrouterKey, model: fallbackModel }
}

/**
 * Instantiate a provider. Uses resolveProvider() to pick the right SDK
 * given the available API keys. All providers implement the same
 * AIProvider interface, so callers don't need to care about routing.
 */
export async function createProvider(providerName, model) {
  const { kind, apiKey, model: resolvedModel } = resolveProvider(providerName, model)
  switch (kind) {
    case 'claude':
    case 'anthropic': {
      const { ClaudeProvider } = await import('../providers/claude.js')
      return new ClaudeProvider(apiKey, resolvedModel)
    }
    case 'openai': {
      const { OpenAIProvider } = await import('../providers/openai.js')
      return new OpenAIProvider(apiKey, resolvedModel)
    }
    case 'gemini': {
      const { GeminiProvider } = await import('../providers/gemini.js')
      return new GeminiProvider(apiKey, resolvedModel)
    }
    case 'openrouter':
    case 'llama': {
      const { LLaMAProvider } = await import('../providers/llama.js')
      return new LLaMAProvider(apiKey, resolvedModel)
    }
    default:
      throw new Error(`Unreachable: unknown provider kind ${kind}`)
  }
}

/**
 * Validate config at startup. Throws if the configured providers cannot
 * be instantiated — catches env-var typos before the first request.
 */
export function validateConfig() {
  const errors = []
  const check = (label, providerName) => {
    try {
      if (!VALID_PROVIDERS.has(providerName)) {
        errors.push(`${label}: unknown provider "${providerName}"`)
        return
      }
      resolveProvider(providerName, 'placeholder')
    } catch (err) {
      errors.push(`${label}: ${err.message}`)
    }
  }
  check('DETECTION', PIPELINE_CONFIG.detection.provider)
  for (const tier of PIPELINE_CONFIG.classification.tiers) {
    check(`CLASSIFICATION ${tier.name}`, tier.provider)
  }
  if (PIPELINE_CONFIG.validation.enabled) {
    check('VALIDATION', PIPELINE_CONFIG.validation.provider)
  }
  if (PIPELINE_CONFIG.labelling.enabled) {
    check('LABELLING', PIPELINE_CONFIG.labelling.suggestProvider)
  }
  return errors
}
