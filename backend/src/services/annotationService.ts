/**
 * Annotation Service
 *
 * Manages the annotation workflow for training data:
 * - Lists images that need annotation
 * - Saves bbox annotations (model + base)
 * - Tracks progress
 * - Exports to YOLO format
 */

import fs from 'fs/promises'
import path from 'path'
import { randomUUID } from 'crypto'
import sharp from 'sharp'
import logger from '../utils/logger'

// Faction label remapping applied at YOLO export time only.
// Existing annotation JSON files are left unchanged — fully reversible.
//
// space_marines:       all loyalist chapter marines collapsed for model accuracy
// chaos_space_marines: all traitor legions collapsed for model accuracy
const EXPORT_LABEL_REMAP: Record<string, string> = {
  // Loyalist chapters → space_marines (one codex in 10th ed).
  blood_angels:     'space_marines',
  dark_angels:      'space_marines',
  space_wolves:     'space_marines',
  black_templars:   'space_marines',
  deathwatch:       'space_marines',
  grey_knights:     'space_marines',
  // Top-level renames (10th ed / historical drift). Without these the
  // annotation corpus contained ~222 files whose faction slug bypassed
  // the remap entirely and produced orphan class names at export — see
  // STATUS.md 2026-04-18 training-data integrity audit.
  custodes:         'adeptus_custodes',
  eldar:            'aeldari',
  genestealer_cult: 'genestealer_cults',
  imperial_guard:   'astra_militarum',
  // NOTE: death_guard / thousand_sons / world_eaters / emperors_children
  // are NOT collapsed here. Each has its own 10th-ed codex and its own
  // class in the deployed yolo11x_run2_best.pt (see runs/yolo11x_run2_best.classes.txt).
  // Keeping them distinct so the model doesn't lose discrimination.
}
function remapExportLabel(label: string): string {
  return EXPORT_LABEL_REMAP[label] ?? label
}

/** Expand a merged faction name back to all raw faction directories it covers. */
function expandFaction(faction: string): string[] {
  const raw = Object.entries(EXPORT_LABEL_REMAP)
    .filter(([, merged]) => merged === faction)
    .map(([original]) => original)
  // If faction is a merged name, include itself + all sub-factions
  // If faction is a raw name, just return it
  return raw.length > 0 ? [faction, ...raw] : [faction]
}

export interface QualityIssue {
  type: 'error' | 'warning'
  code: 'BBOX_OUT_OF_BOUNDS' | 'BBOX_TOO_SMALL' | 'DUPLICATE_BOX'
  message: string
  bboxId?: string
}

export interface ImageAnnotation {
  imageId: string
  imagePath: string
  faction: string
  source: string
  width: number
  height: number
  annotations: BboxAnnotationData[]
  // AI prediction validation data (for training improvements)
  rejectedPredictions?: RejectedPrediction[]  // False positives for hard negative mining
  redrawnPredictions?: RejectedPrediction[]   // Wrong boxes that were corrected
  annotatedAt: string
  annotatedBy: string
}

export interface BboxAnnotationData {
  id: string
  modelBbox: {
    x: number  // Pixels
    y: number
    width: number
    height: number
  }
  baseBbox?: {
    x: number
    y: number
    width: number
    height: number
  }
  classLabel: string  // Faction slug (e.g., "space_marines"). Feeds YOLO
                       // export — legacy name, semantically a faction.
  unit_slug?: string   // Optional: canonical unit slug within the faction
                       // (e.g., "intercessors"). Empty/absent = "I know
                       // the faction but haven't identified the unit yet"
                       // — same deferred-labelling pattern as the
                       // warhammer-analyzer audit pile. Sourced from
                       // scripts/data/units.json via the taxonomy endpoint.
  confidence?: number
  // AI prediction tracking
  validationAction?: 'accepted' | 'rejected' | 'redrawn'
  originalPrediction?: boolean  // Was this from AI?
}

export interface RejectedPrediction {
  id: string
  modelBbox: {
    x: number
    y: number
    width: number
    height: number
  }
  classLabel: string
  confidence?: number
}

/** Status values accepted by `getNextImage` and `GET /api/annotate/next?status=`.
 *  Mirrors STATUS_VALUES in backend/src/index.ts. */
export type AnnotatorStatus =
  | 'unannotated'
  | 'pending'
  | 'legacy'
  | 'pseudo'
  | 'flagged'
  | 'frozen_eval'
  | 'all'
  | 'gw_walk'

/** Row shape returned by every per-status picker helper. Same fields
 *  as getImageList's element so they're freely interchangeable. */
type QueueImage = {
  imageId: string
  imagePath: string
  faction: string
  source: string
  isAnnotated: boolean
}

export interface AnnotationProgress {
  totalImages: number
  annotatedImages: number
  percentComplete: number
  pendingImages: number
  legacyImages: number
  flaggedImages: number
  byFaction: Record<string, { total: number; annotated: number; pending: number; legacy: number; flagged: number }>
}

export class AnnotationService {
  private trainingDataPath: string
  private annotationsPath: string
  /** Sources the annotator browses, in priority order. Configured by
   *  `ANNOTATION_SOURCES` env var (comma-separated). Public so the route
   *  layer can surface the list to the frontend's source picker without
   *  hardcoding it. */
  get allowedSources(): string[] {
    // `cmon` covers CoolMiniOrNot scenes symlinked in by
    // `scripts/seed_cmon_for_annotator.py`. The script buckets each
    // CMON scene under its best-guess faction (via
    // photoanalyzer.label.weak.classify_title) and drops anything
    // unclassifiable into backend/training_data/_unknown/cmon/.
    const sources = process.env.ANNOTATION_SOURCES ?? 'reddit,dakkadakka,cmon'
    return sources.split(',').map(s => s.trim()).filter(Boolean)
  }
  public onAnnotationSaved: (() => void) | null = null

  // Image list cache — avoids walking 25k files on every request.
  // Two variants: unannotated-only (the hot path for `/next?status=unannotated`)
  // and include-annotated (used by getProgress, _buildCompletionLists, export).
  // Both are cleared on every save.
  private imageListCache: Array<{
    imageId: string; imagePath: string
    faction: string; source: string; isAnnotated: boolean
  }> | null = null
  private imageListCacheAll: Array<{
    imageId: string; imagePath: string
    faction: string; source: string; isAnnotated: boolean
  }> | null = null
  // In-flight promise guards — when a save invalidates the caches and the
  // frontend immediately fires prefetch + progress + loadNext in parallel,
  // all three would otherwise kick off their own full fs walk. Coalesce
  // them onto a single rebuild promise.
  private imageListInFlight: Promise<Array<{
    imageId: string; imagePath: string
    faction: string; source: string; isAnnotated: boolean
  }>> | null = null
  private imageListAllInFlight: Promise<Array<{
    imageId: string; imagePath: string
    faction: string; source: string; isAnnotated: boolean
  }>> | null = null
  private completionListsInFlight: Promise<{
    pending: Array<{ imageId: string; imagePath: string; faction: string; source: string; isAnnotated: boolean }>
    legacy: Array<{ imageId: string; imagePath: string; faction: string; source: string; isAnnotated: boolean }>
    pseudo: Array<{ imageId: string; imagePath: string; faction: string; source: string; isAnnotated: boolean }>
  }> | null = null

  // Permanent path map — populated during any getImageList() scan, never cleared.
  // Image paths never change, so no invalidation needed.
  // Lets the image endpoint skip the full 36k-fs-call scan to find one file.
  private imagePathMap = new Map<string, { imagePath: string; faction: string; source: string }>()

  // Per-image reservations: imageId → { userId, expiresAt }.
  // Prevents two annotators from being served the same image simultaneously.
  private reservations = new Map<string, { userId: string; expiresAt: number }>()
  private readonly RESERVATION_TTL_MS = 15 * 60 * 1000  // 15 minutes

  // Cached set of imageIds that have DINO proposals. Refreshed periodically.
  private proposalIds: Set<string> | null = null
  private proposalIdsCacheTime = 0
  private readonly PROPOSAL_CACHE_TTL_MS = 60 * 1000  // 60 seconds
  private proposalsPath: string

  // Phase C frozen-eval manifest, lazily loaded once per process. The 200
  // imageIds in data/scene_benchmark/eval_200.json are the held-out test
  // set — `?status=frozen_eval` cycles only these for visual review.
  private frozenEvalIds: Set<string> | null = null

  constructor() {
    // All paths configurable via env — allows running a parallel clean-reference instance
    const dataDir = process.env.TRAINING_DATA_PATH
      ? path.resolve(process.env.TRAINING_DATA_PATH)
      : path.join(__dirname, '../../training_data')
    const annotDir = process.env.ANNOTATIONS_PATH
      ? path.resolve(process.env.ANNOTATIONS_PATH)
      : path.join(__dirname, '../../training_data_annotations')
    const proposalsDir = process.env.PROPOSALS_PATH
      ? path.resolve(process.env.PROPOSALS_PATH)
      : path.join(__dirname, '../../training_data_proposals')
    this.trainingDataPath = dataDir
    this.annotationsPath = annotDir
    this.proposalsPath = proposalsDir
  }

  /** Fetch the candidate queue for a given status filter. Each branch
   *  returns the same `QueueImage[]` shape so downstream sort / dedup /
   *  reservation logic doesn't care which branch produced it.
   *
   *  Per-status semantics:
   *    unannotated → fast-path cache of fresh, un-touched images
   *    pending     → annotated but missing unit_slug on ≥1 bbox
   *    legacy      → grandfathered incomplete (legacy_no_unit=true)
   *    pseudo      → Phase F1 auto-labels awaiting box review
   *    flagged     → .skip.json sidecars (browse-only)
   *    frozen_eval → Phase C held-out 200 (browse-only)
   *    all         → pending > legacy > unannotated, deduped by id
   *    gw_walk     → Phase B reference walkthrough — gw_shop images only,
   *                  sorted by folder_slug then filename so the user
   *                  walks unit-by-unit; unannotated AND unflagged
   */
  private async _pickByStatus(
    status: AnnotatorStatus,
    sourceSet: Set<string> | undefined,
  ): Promise<QueueImage[]> {
    switch (status) {
      case 'pending':     return this.getPendingImageList()
      case 'legacy':      return this.getLegacyImageList()
      case 'pseudo':      return this.getPseudoImageList()
      case 'flagged':     return this.getFlaggedImageList()
      case 'frozen_eval': return this._pickFrozenEval()
      case 'all':         return this._pickAll(sourceSet)
      case 'unannotated': return this.getImageList(false, sourceSet)
      case 'gw_walk':     return this._pickGwWalk()
      default: {
        const _exhaustive: never = status
        throw new Error(`Unhandled status: ${_exhaustive}`)
      }
    }
  }

  /** Phase B reference walkthrough. Walks training_data/{faction}/gw_shop/
   *  symlinks, sorted so the user sees images grouped by unit folder
   *  (lead → feature → stock for the same product appear consecutively).
   *  Filters out already-annotated and flagged-as-unusable images. */
  private async _pickGwWalk(): Promise<QueueImage[]> {
    const all = await this.getImageList(true)
    const gwOnly = all.filter(img => img.source === 'gw_shop' && !img.isAnnotated)
    // Imageids come from the symlink filename, which encodes the gw_shop
    // folder slug as `{folder}__{rest}`. Sorting by imageId therefore
    // groups every variant of one product (lead/feature/stock) together.
    return [...gwOnly].sort((a, b) => a.imageId.localeCompare(b.imageId))
  }

  /** Phase C held-out 200. Source imageIds from the manifest, then
   *  resolve through getImageList(true,…) so faction / source /
   *  imagePath fields come back populated identically to other modes. */
  private async _pickFrozenEval(): Promise<QueueImage[]> {
    const frozenIds = await this.getFrozenEvalIds()
    const full = await this.getImageList(true)
    return full.filter(img => frozenIds.has(img.imageId))
  }

  /** Merged "everything" queue: pending → legacy → unannotated, deduped
   *  by imageId. Priority order keeps the user on active backfill work
   *  before fresh images appear. */
  private async _pickAll(sourceSet: Set<string> | undefined): Promise<QueueImage[]> {
    const [unann, pending, legacy] = await Promise.all([
      this.getImageList(false, sourceSet),
      this.getPendingImageList(),
      this.getLegacyImageList(),
    ])
    const seen = new Set<string>()
    const out: QueueImage[] = []
    for (const img of pending) if (!seen.has(img.imageId)) { seen.add(img.imageId); out.push(img) }
    for (const img of legacy)  if (!seen.has(img.imageId)) { seen.add(img.imageId); out.push(img) }
    for (const img of unann)   if (!seen.has(img.imageId)) { seen.add(img.imageId); out.push(img) }
    return out
  }

  /** Load the Phase C frozen-eval manifest once and cache the imageId set. */
  private async getFrozenEvalIds(): Promise<Set<string>> {
    if (this.frozenEvalIds) return this.frozenEvalIds
    const manifestPath = path.join(__dirname, '../../../data/scene_benchmark/eval_200.json')
    const raw = await fs.readFile(manifestPath, 'utf-8')
    const manifest = JSON.parse(raw) as { images: Array<{ imageId: string }> }
    this.frozenEvalIds = new Set(manifest.images.map(im => im.imageId))
    return this.frozenEvalIds
  }

  /** Load the set of imageIds that have pre-computed DINO proposals. */
  private async getProposalIds(): Promise<Set<string>> {
    const now = Date.now()
    if (this.proposalIds && now - this.proposalIdsCacheTime < this.PROPOSAL_CACHE_TTL_MS) {
      return this.proposalIds
    }
    const ids = new Set<string>()
    try {
      const files = await fs.readdir(this.proposalsPath)
      for (const f of files) {
        if (f.endsWith('.json')) ids.add(f.replace('.json', ''))
      }
    } catch {
      // proposals dir doesn't exist yet — empty set
    }
    this.proposalIds = ids
    this.proposalIdsCacheTime = now
    return ids
  }

  // ── Reservation helpers ────────────────────────────────────────────────────

  private cleanExpiredReservations(): void {
    const now = Date.now()
    for (const [id, res] of this.reservations) {
      if (now > res.expiresAt) this.reservations.delete(id)
    }
  }

  reserveImage(imageId: string, userId: string): void {
    this.reservations.set(imageId, { userId, expiresAt: Date.now() + this.RESERVATION_TTL_MS })
  }

  clearReservation(imageId: string): void {
    this.reservations.delete(imageId)
  }

  getActiveReservations(): Array<{ imageId: string; userId: string; expiresAt: number }> {
    this.cleanExpiredReservations()
    return Array.from(this.reservations.entries()).map(([imageId, res]) => ({ imageId, ...res }))
  }

  /**
   * Initialize annotation system
   * Creates annotations directory if it doesn't exist
   */
  async initialize(): Promise<void> {
    try {
      await fs.mkdir(this.annotationsPath, { recursive: true })
      // Warm the image list cache and path map on startup so the first annotator
      // request is instant rather than triggering a cold 18k-file scan.
      await this.getImageList(false)
      logger.info('📝 Annotation service initialized')
    } catch (error) {
      logger.error('Failed to initialize annotation service:', error)
      throw error
    }
  }

  // Per-faction image caps — target 400 annotations per faction
  private factionLimits: Record<string, number> = {
    default: 400,
  }

  private getFactionLimit(faction: string): number {
    return this.factionLimits[faction] ?? this.factionLimits.default
  }

  // Kept for progress calculation
  private get perFactionLimit(): number {
    return this.factionLimits.default
  }

  /**
   * Get list of all images available for annotation
   * Returns image metadata including path, faction, source.
   *
   * Capped at `perFactionLimit` (400) images per faction for focused
   * annotation. When `sourceFilter` is provided, the scan walks ONLY
   * those source subdirs — and the cap is spent entirely on the
   * filtered source. That's the whole point: without this override, an
   * abundant source like `ebay` would fill the 400-cap for a faction
   * before the user's filtered source (`cmon`) got a look-in, and
   * filtering to `cmon` would return zero images in that faction.
   *
   * `sourceFilter=undefined` uses the default walk (all sources in env
   * priority order) and populates the cached unannotated list.
   * `sourceFilter=Set(...)` bypasses the cache (cheap enough on demand).
   */
  async getImageList(
    includeAnnotated: boolean = false,
    sourceFilter?: Set<string>,
  ): Promise<Array<{
    imageId: string
    imagePath: string
    faction: string
    source: string
    isAnnotated: boolean
  }>> {
    // Cache fast-path only applies to the default scan (no source filter).
    if (!sourceFilter) {
      if (!includeAnnotated && this.imageListCache) return this.imageListCache
      if (includeAnnotated && this.imageListCacheAll) return this.imageListCacheAll
      // In-flight coalescing: if a rebuild is already running, piggy-back
      // on it instead of kicking off a second full fs walk.
      if (!includeAnnotated && this.imageListInFlight) return this.imageListInFlight
      if (includeAnnotated && this.imageListAllInFlight) return this.imageListAllInFlight
    }

    const scanPromise = this._scanImageList(includeAnnotated, sourceFilter)
    if (!sourceFilter) {
      if (includeAnnotated) this.imageListAllInFlight = scanPromise
      else this.imageListInFlight = scanPromise
      try {
        return await scanPromise
      } finally {
        if (includeAnnotated) this.imageListAllInFlight = null
        else this.imageListInFlight = null
      }
    }
    return scanPromise
  }

  private async _scanImageList(
    includeAnnotated: boolean,
    sourceFilter?: Set<string>,
  ): Promise<Array<{
    imageId: string
    imagePath: string
    faction: string
    source: string
    isAnnotated: boolean
  }>> {
    const images: Array<{
      imageId: string
      imagePath: string
      faction: string
      source: string
      isAnnotated: boolean
    }> = []

    // Track count per faction
    const factionCounts: Record<string, number> = {}

    // Sources to walk: filter narrows the scan AND the cap budget — a
    // call with sourceFilter={cmon} gets the whole 400-cap per faction
    // spent on cmon, instead of being starved by ebay/isolation first.
    const sourcesToWalk = sourceFilter
      ? this.allowedSources.filter(s => sourceFilter.has(s))
      : this.allowedSources

    try {
      const factions = await fs.readdir(this.trainingDataPath)

      for (const faction of factions) {
        const factionPath = path.join(this.trainingDataPath, faction)
        const stat = await fs.stat(factionPath)

        if (!stat.isDirectory()) continue
        if (faction === 'hormagaunts' || faction === 'tyranid_ripper_swarm') continue
        if (faction === 'reddit' || faction === 'dakkadakka') continue  // Skip non-faction dirs

        factionCounts[faction] = 0

        // Check configured source subdirectories
        for (const source of sourcesToWalk) {
          const sourcePath = path.join(factionPath, source)

          try {
            const files = await fs.readdir(sourcePath)

            for (const file of files) {
              // Stop if we've hit the limit for this faction
              if (factionCounts[faction] >= this.getFactionLimit(faction)) break

              if (!file.match(/\.(jpg|jpeg|png|gif|webp)$/i)) continue

              const imagePath = path.join(sourcePath, file)
              const imageId = this.getImageId(imagePath)

              // Skip flagged images entirely
              const isFlagged = await this.isImageFlagged(imageId)
              if (isFlagged) continue

              const isAnnotated = await this.isImageAnnotated(imageId)

              // Count ALL images toward limit (not just filtered ones)
              factionCounts[faction]++

              // Populate permanent path map (paths never change)
              if (!this.imagePathMap.has(imageId)) {
                this.imagePathMap.set(imageId, { imagePath, faction, source })
              }

              // But only add to results if it matches the filter
              if (includeAnnotated || !isAnnotated) {
                images.push({
                  imageId,
                  imagePath,
                  faction,
                  source,
                  isAnnotated
                })
              }
            }
          } catch (error) {
            // Source directory doesn't exist, skip
            continue
          }
        }
      }

      logger.info(
        `📋 Found ${images.length} images (${this.perFactionLimit}/faction, ` +
        `includeAnnotated: ${includeAnnotated}` +
        (sourceFilter ? `, sourceFilter: ${[...sourceFilter].join(',')}` : '') +
        `)`
      )

      // Only cache the DEFAULT scan (no source filter). Filtered scans
      // are rarer and each has its own cap math, so recomputing is fine.
      if (!sourceFilter) {
        if (includeAnnotated) this.imageListCacheAll = images
        else this.imageListCache = images
      }

      return images
    } catch (error) {
      logger.error('Error getting image list:', error)
      throw error
    }
  }

  /**
   * Get next unannotated image
   * When prioritize=true, delegates to active learning service for confidence-based ordering
   * Returns null if all images are annotated
   */
  async getNextImage(
    prioritize: boolean = false,
    faction?: string,
    userId?: string,
    exclude?: string[],
    sources?: string[],
    status: AnnotatorStatus = 'unannotated',
  ): Promise<{
    imageId: string
    imagePath: string
    faction: string
    source: string
    confidenceScore?: number
  } | null> {
    this.cleanExpiredReservations()

    // Source filter: when the caller has specified one, narrow the scan
    // to just those sources AND spend the per-faction cap on them —
    // otherwise an abundant source (ebay) saturates the cap first and
    // a filter on a less-abundant source (cmon) returns nothing.
    const sourceSet = sources && sources.length > 0 ? new Set(sources) : undefined

    let images = await this._pickByStatus(status, sourceSet)
    if (faction) {
      const factionSet = new Set(expandFaction(faction))
      images = images.filter(img => factionSet.has(img.faction))
    }
    // Source filter — same shape as the faction filter. Empty / undefined
    // = no filter. The list of allowed sources is whatever `allowedSources`
    // already enumerates; we just narrow within that.
    if (sources && sources.length > 0) {
      const sourceSet = new Set(sources)
      images = images.filter(img => sourceSet.has(img.source))
    }

    // Filter out images reserved by a different user.
    // A user may be re-sent their own currently-reserved image (e.g. on page reload).
    images = images.filter(img => {
      const res = this.reservations.get(img.imageId)
      return !res || res.userId === userId
    })

    if (images.length === 0) return null

    // For pending/legacy/flagged modes the user wants to revisit ALL
    // matching items — they already know what they're looking for, no
    // need to prioritise by DINO proposals. Sort stably by imageId.
    if (status === 'pending' || status === 'legacy' || status === 'pseudo' || status === 'flagged' || status === 'frozen_eval') {
      images.sort((a, b) => a.imageId.localeCompare(b.imageId))
    } else {
      // Only serve images that have pre-computed proposals, sorted by imageId
      // so the same unit clusters together (imageId encodes faction + unit name).
      const proposalIds = await this.getProposalIds()
      const withProposals = images.filter(img => proposalIds.has(img.imageId))
      if (withProposals.length > 0) {
        withProposals.sort((a, b) => a.imageId.localeCompare(b.imageId))
        images = withProposals
      }
      // If no proposals exist yet, fall through to the full list (first-run scenario)
    }

    // Move session-skipped images to the back of the queue (must run after sort)
    if (exclude?.length) {
      const excludeSet = new Set(exclude)
      const notSkipped = images.filter(img => !excludeSet.has(img.imageId))
      const skipped    = images.filter(img =>  excludeSet.has(img.imageId))
      images = [...notSkipped, ...skipped]
    }

    let chosen: typeof images[0]

    if (prioritize) {
      try {
        const { activeLearningService } = await import('./activeLearningService')
        const prioritized = activeLearningService.getNextPrioritizedImage(images as any)
        chosen = (prioritized as typeof images[0]) ?? images[0]
      } catch {
        chosen = images[0]
      }
    } else {
      chosen = images[0]
    }

    // Reserve this image for the requesting user
    if (userId) this.reserveImage(chosen.imageId, userId)

    return chosen
  }

  /**
   * Validate annotation quality
   * Returns list of errors and warnings
   */
  async validateAnnotation(annotation: ImageAnnotation): Promise<QualityIssue[]> {
    const issues: QualityIssue[] = []

    try {
      // Get image dimensions
      const metadata = await sharp(annotation.imagePath).metadata()
      const imgWidth = metadata.width!
      const imgHeight = metadata.height!

      for (const bbox of annotation.annotations) {
        const model = bbox.modelBbox

        // 1. Check model bbox is within image bounds
        if (
          model.x < 0 ||
          model.y < 0 ||
          model.x + model.width > imgWidth ||
          model.y + model.height > imgHeight
        ) {
          issues.push({
            type: 'error',
            code: 'BBOX_OUT_OF_BOUNDS',
            message: `Model bbox extends beyond image (${model.x},${model.y} ${model.width}x${model.height})`,
            bboxId: bbox.id,
          })
        }

        // 2. Check minimum size (avoid tiny accidental boxes)
        if (model.width < 10 || model.height < 10) {
          issues.push({
            type: 'warning',
            code: 'BBOX_TOO_SMALL',
            message: `Bbox very small (${model.width}x${model.height}px)`,
            bboxId: bbox.id,
          })
        }
      }

      // 3. Check for duplicate/overlapping boxes
      for (let i = 0; i < annotation.annotations.length; i++) {
        for (let j = i + 1; j < annotation.annotations.length; j++) {
          const iou = this.calculateIoU(
            annotation.annotations[i].modelBbox,
            annotation.annotations[j].modelBbox
          )

          if (iou > 0.9) {
            // 90%+ overlap = likely duplicate
            issues.push({
              type: 'warning',
              code: 'DUPLICATE_BOX',
              message: `High overlap (${(iou * 100).toFixed(0)}%) between boxes`,
              bboxId: annotation.annotations[i].id,
            })
          }
        }
      }
    } catch (error) {
      logger.error('Error validating annotation:', error)
      // Don't throw - return validation error as issue
      issues.push({
        type: 'error',
        code: 'BBOX_OUT_OF_BOUNDS',
        message: `Failed to validate: ${error instanceof Error ? error.message : 'Unknown error'}`,
      })
    }

    return issues
  }

  /**
   * Validate all saved annotations
   * Returns summary of issues across entire dataset
   */
  async validateAllAnnotations(): Promise<{
    totalAnnotations: number
    validAnnotations: number
    invalidAnnotations: number
    warningAnnotations: number
    totalErrors: number
    totalWarnings: number
    issues: Array<{
      imageId: string
      imagePath: string
      errors: QualityIssue[]
      warnings: QualityIssue[]
    }>
  }> {
    logger.info('🔍 Validating all annotations...')

    const images = await this.getImageList(true)
    const annotatedImages = images.filter(img => img.isAnnotated)

    let validCount = 0
    let invalidCount = 0
    let warningCount = 0
    let totalErrors = 0
    let totalWarnings = 0
    const issues: Array<{
      imageId: string
      imagePath: string
      errors: QualityIssue[]
      warnings: QualityIssue[]
    }> = []

    for (const img of annotatedImages) {
      const annotation = await this.getAnnotation(img.imageId)
      if (!annotation) continue

      const validationIssues = await this.validateAnnotation(annotation)
      const errors = validationIssues.filter(i => i.type === 'error')
      const warnings = validationIssues.filter(i => i.type === 'warning')

      if (errors.length > 0) {
        invalidCount++
        totalErrors += errors.length
      } else if (warnings.length > 0) {
        warningCount++
        validCount++
      } else {
        validCount++
      }

      totalWarnings += warnings.length

      if (errors.length > 0 || warnings.length > 0) {
        issues.push({
          imageId: img.imageId,
          imagePath: img.imagePath,
          errors,
          warnings,
        })
      }
    }

    logger.info(`✅ Validation complete: ${validCount}/${annotatedImages.length} valid, ${invalidCount} invalid, ${warningCount} with warnings`)

    return {
      totalAnnotations: annotatedImages.length,
      validAnnotations: validCount,
      invalidAnnotations: invalidCount,
      warningAnnotations: warningCount,
      totalErrors,
      totalWarnings,
      issues,
    }
  }

  /**
   * Calculate Intersection over Union for two bboxes
   */
  private calculateIoU(
    a: { x: number; y: number; width: number; height: number },
    b: { x: number; y: number; width: number; height: number }
  ): number {
    // Convert to x1, y1, x2, y2
    const a_x1 = a.x
    const a_y1 = a.y
    const a_x2 = a.x + a.width
    const a_y2 = a.y + a.height

    const b_x1 = b.x
    const b_y1 = b.y
    const b_x2 = b.x + b.width
    const b_y2 = b.y + b.height

    // Calculate intersection
    const x1 = Math.max(a_x1, b_x1)
    const y1 = Math.max(a_y1, b_y1)
    const x2 = Math.min(a_x2, b_x2)
    const y2 = Math.min(a_y2, b_y2)

    if (x2 < x1 || y2 < y1) return 0 // No overlap

    const intersection = (x2 - x1) * (y2 - y1)
    const areaA = a.width * a.height
    const areaB = b.width * b.height
    const union = areaA + areaB - intersection

    return intersection / union
  }

  /**
   * Save annotation for an image
   */
  async saveAnnotation(annotation: ImageAnnotation): Promise<void> {
    try {
      const annotationPath = this.getAnnotationPath(annotation.imageId)
      const annotationDir = path.dirname(annotationPath)

      // Create directory if it doesn't exist
      await fs.mkdir(annotationDir, { recursive: true })

      // If every bbox agrees on one non-empty classLabel, promote it to
      // the annotation's canonical `faction`. This decouples "where the
      // file lives on disk" (folder-derived, immutable) from "what
      // faction it really is" (user-labelled). Mixed-army shots keep
      // whatever the caller sent (typically the folder default).
      const labels = new Set(
        (annotation.annotations ?? [])
          .map(a => (a.classLabel ?? '').trim())
          .filter(Boolean),
      )
      if (labels.size === 1) {
        annotation.faction = [...labels][0]
      }

      // Save annotation as JSON
      await fs.writeFile(
        annotationPath,
        JSON.stringify(annotation, null, 2),
        'utf-8'
      )

      const rejectedCount = annotation.rejectedPredictions?.length || 0
      const redrawnCount = annotation.redrawnPredictions?.length || 0
      const aiAccepted = annotation.annotations.filter(a => a.originalPrediction).length
      logger.info(`✅ Saved annotation for ${annotation.imageId} (${annotation.annotations.length} boxes, ${aiAccepted} AI-accepted, ${rejectedCount} rejected, ${redrawnCount} redrawn)`)

      // Update imageList caches incrementally — saves a ~700ms full fs
      // rescan per save. The saved image's identity and metadata are
      // known, so we can surgically remove it from the unannotated list
      // and mark it annotated in the all-list.
      if (this.imageListCache) {
        this.imageListCache = this.imageListCache.filter(
          img => img.imageId !== annotation.imageId,
        )
      }
      if (this.imageListCacheAll) {
        const entry = this.imageListCacheAll.find(
          img => img.imageId === annotation.imageId,
        )
        if (entry) entry.isAnnotated = true
      }
      // Pending/legacy/pseudo bucket membership may have changed — a
      // save can move an image between buckets (e.g. pseudo → pending
      // when a F1 review saves without unit_slugs, or pending → complete
      // when the last unit_slug is filled in). Invalidate the three
      // buckets so `_buildCompletionLists` re-classifies; thanks to the
      // preserved imageListCacheAll above, that rebuild skips the fs
      // walk and just re-reads annotation JSONs (~200ms).
      this.pendingListCache = null
      this.legacyListCache = null
      this.pseudoListCache = null
      this.clearReservation(annotation.imageId)

      // Invalidate dashboard cache
      if (this.onAnnotationSaved) {
        this.onAnnotationSaved()
      }
    } catch (error) {
      logger.error('Error saving annotation:', error)
      throw error
    }
  }

  /**
   * Get annotation for an image
   * Returns null if image is not annotated
   */
  async getAnnotation(imageId: string): Promise<ImageAnnotation | null> {
    try {
      const annotationPath = this.getAnnotationPath(imageId)
      const data = await fs.readFile(annotationPath, 'utf-8')
      return JSON.parse(data)
    } catch (error) {
      // Annotation doesn't exist
      return null
    }
  }

  /**
   * Check if image is annotated
   */
  getImageMeta(imageId: string): { imagePath: string; faction: string; source: string } | undefined {
    return this.imagePathMap.get(imageId)
  }

  async isImageAnnotated(imageId: string): Promise<boolean> {
    const annotationPath = this.getAnnotationPath(imageId)
    try {
      await fs.access(annotationPath)
      return true
    } catch {
      return false
    }
  }

  /**
   * Classify an annotated image by its "completeness" relative to the
   * unit_slug field. One disk read per call; callers batch through the
   * higher-level list caches below.
   *
   * Returns:
   *   'complete' — every bbox has a non-empty unit_slug
   *   'pending'  — at least one bbox is missing unit_slug, file is NOT
   *                flagged `legacy_no_unit`. The active work-queue for
   *                the user to come back and finish.
   *   'legacy'   — file has `legacy_no_unit: true` (grandfathered —
   *                annotated before unit_slug existed). Surfaces in
   *                its own filter so the user can batch-backfill when
   *                they want to, without flooding Pending.
   *   'empty'    — no bboxes (shouldn't normally be saved, but handle).
   *   null       — no annotation file (image is still unannotated) or
   *                JSON parse error.
   */
  async classifyAnnotation(imageId: string): Promise<
    'complete' | 'pending' | 'legacy' | 'pseudo' | 'empty' | null
  > {
    const annotationPath = this.getAnnotationPath(imageId)
    try {
      const raw = await fs.readFile(annotationPath, 'utf-8')
      const parsed = JSON.parse(raw) as {
        annotations?: Array<{ unit_slug?: string }>
        legacy_no_unit?: boolean
        pseudoLabelled?: boolean
      }
      const anns = parsed.annotations ?? []
      if (anns.length === 0) return 'empty'
      // Pseudo-labelled annotations (Phase F1 auto-label output) go in
      // their own bucket so the Pending queue stays clean. Saving via
      // the annotator drops the pseudoLabelled flag, promoting them
      // into pending/complete on the next pass.
      if (parsed.pseudoLabelled === true) return 'pseudo'
      const hasMissing = anns.some(a => !a.unit_slug || !String(a.unit_slug).trim())
      if (!hasMissing) return 'complete'
      return parsed.legacy_no_unit === true ? 'legacy' : 'pending'
    } catch {
      return null
    }
  }

  /** Back-compat alias — callers that still import the old name. */
  async isImagePending(imageId: string): Promise<boolean> {
    return (await this.classifyAnnotation(imageId)) === 'pending'
  }

  /** Cached list of images in a given completion state (pending or
   *  legacy). Built lazily on first request, invalidated whenever a
   *  save lands. Shape mirrors imageListCache so the queue/filter path
   *  is symmetric. */
  private pendingListCache: Array<{
    imageId: string; imagePath: string
    faction: string; source: string; isAnnotated: boolean
  }> | null = null
  private legacyListCache: Array<{
    imageId: string; imagePath: string
    faction: string; source: string; isAnnotated: boolean
  }> | null = null
  private pseudoListCache: Array<{
    imageId: string; imagePath: string
    faction: string; source: string; isAnnotated: boolean
  }> | null = null

  async getPendingImageList(): Promise<Array<{
    imageId: string
    imagePath: string
    faction: string
    source: string
    isAnnotated: boolean
  }>> {
    if (this.pendingListCache) return this.pendingListCache
    const { pending } = await this._buildCompletionLists()
    return pending
  }

  async getLegacyImageList(): Promise<Array<{
    imageId: string
    imagePath: string
    faction: string
    source: string
    isAnnotated: boolean
  }>> {
    if (this.legacyListCache) return this.legacyListCache
    const { legacy } = await this._buildCompletionLists()
    return legacy
  }

  async getPseudoImageList(): Promise<Array<{
    imageId: string
    imagePath: string
    faction: string
    source: string
    isAnnotated: boolean
  }>> {
    if (this.pseudoListCache) return this.pseudoListCache
    const { pseudo } = await this._buildCompletionLists()
    return pseudo
  }

  /** Walk every annotated image and bucket it into pending / legacy /
   *  complete based on `classifyAnnotation`. One scan fills all three
   *  caches; subsequent calls return from cache until the next save
   *  invalidates via saveAnnotation. Concurrent callers (e.g. progress
   *  endpoint fires getPending+getLegacy+getFlagged in Promise.all) share
   *  a single in-flight promise instead of each doing their own scan. */
  private async _buildCompletionLists(): Promise<{
    pending: Array<{ imageId: string; imagePath: string; faction: string; source: string; isAnnotated: boolean }>
    legacy: Array<{ imageId: string; imagePath: string; faction: string; source: string; isAnnotated: boolean }>
    pseudo: Array<{ imageId: string; imagePath: string; faction: string; source: string; isAnnotated: boolean }>
  }> {
    if (this.completionListsInFlight) return this.completionListsInFlight
    const build = (async () => {
      const all = await this.getImageList(true)
      const pending: typeof all = []
      const legacy: typeof all = []
      const pseudo: typeof all = []
      const BATCH = 32
      for (let i = 0; i < all.length; i += BATCH) {
        const batch = all.slice(i, i + BATCH)
        const results = await Promise.all(batch.map(async (img) => {
          if (!img.isAnnotated) return null
          return { img, cls: await this.classifyAnnotation(img.imageId) }
        }))
        for (const r of results) {
          if (!r) continue
          if (r.cls === 'pending') pending.push(r.img)
          else if (r.cls === 'legacy') legacy.push(r.img)
          else if (r.cls === 'pseudo') pseudo.push(r.img)
        }
      }
      this.pendingListCache = pending
      this.legacyListCache = legacy
      this.pseudoListCache = pseudo
      return { pending, legacy, pseudo }
    })()
    this.completionListsInFlight = build
    try {
      return await build
    } finally {
      this.completionListsInFlight = null
    }
  }

  /**
   * Check if an image is flagged as unusable
   */
  async isImageFlagged(imageId: string): Promise<boolean> {
    const flagPath = path.join(this.annotationsPath, `${imageId}.skip.json`)
    try {
      await fs.access(flagPath)
      return true
    } catch {
      return false
    }
  }

  /**
   * Flag an image as unusable (permanently skip it). Writes a
   * `<imageId>.skip.json` sidecar — the original image and any
   * annotation JSON stay on disk. Invalidates caches so the queue
   * reflects the new state on the next `/next` call.
   */
  async flagImage(imageId: string, reason?: string): Promise<void> {
    const flagPath = path.join(this.annotationsPath, `${imageId}.skip.json`)
    const flagData = {
      imageId,
      flaggedAt: new Date().toISOString(),
      reason: reason || 'unusable',
    }
    await fs.writeFile(flagPath, JSON.stringify(flagData, null, 2))
    // Flagged images are excluded from the image lists entirely (the
    // main getImageList skips anything with a .skip.json sidecar). Remove
    // the image surgically from each cache instead of nuking them all.
    if (this.imageListCache) {
      this.imageListCache = this.imageListCache.filter(img => img.imageId !== imageId)
    }
    if (this.imageListCacheAll) {
      this.imageListCacheAll = this.imageListCacheAll.filter(img => img.imageId !== imageId)
    }
    if (this.pendingListCache) {
      this.pendingListCache = this.pendingListCache.filter(img => img.imageId !== imageId)
    }
    if (this.legacyListCache) {
      this.legacyListCache = this.legacyListCache.filter(img => img.imageId !== imageId)
    }
    if (this.pseudoListCache) {
      this.pseudoListCache = this.pseudoListCache.filter(img => img.imageId !== imageId)
    }
    // flaggedListCache now has a new entry; rebuild lazily on next read
    // (the browse-flagged flow is cold-cache tolerant and reads it once).
    this.flaggedListCache = null
    logger.info(`🚫 Flagged image ${imageId}: ${flagData.reason}`)
  }

  /**
   * Un-flag a previously-flagged image. Deletes the `.skip.json`
   * sidecar; the image returns to whichever queue it was in (typically
   * unannotated unless there's also an annotation JSON).
   * Idempotent — no-op if the image isn't flagged.
   */
  async unflagImage(imageId: string): Promise<void> {
    const flagPath = path.join(this.annotationsPath, `${imageId}.skip.json`)
    try {
      await fs.unlink(flagPath)
      this.imageListCache = null
      this.imageListCacheAll = null
      this.pendingListCache = null
      this.legacyListCache = null
      this.pseudoListCache = null
      this.flaggedListCache = null
      logger.info(`↩ Un-flagged image ${imageId}`)
    } catch (err: any) {
      if (err.code === 'ENOENT') {
        // Already not flagged — treat as idempotent success.
        return
      }
      throw err
    }
  }

  /** Cache of flagged (skip.json) entries keyed by imageId so the
   *  `status=flagged` filter + unflag UI don't re-walk the filesystem
   *  on every /next call. Invalidated on flag/unflag. */
  private flaggedListCache: Array<{
    imageId: string; imagePath: string
    faction: string; source: string; isAnnotated: boolean
    reason?: string; flaggedAt?: string
  }> | null = null

  async getFlaggedImageList(): Promise<Array<{
    imageId: string
    imagePath: string
    faction: string
    source: string
    isAnnotated: boolean
    reason?: string
    flaggedAt?: string
  }>> {
    if (this.flaggedListCache) return this.flaggedListCache
    const out: Array<{
      imageId: string; imagePath: string; faction: string; source: string
      isAnnotated: boolean; reason?: string; flaggedAt?: string
    }> = []
    try {
      const files = await fs.readdir(this.annotationsPath)
      const skipFiles = files.filter(f => f.endsWith('.skip.json'))
      for (const file of skipFiles) {
        const imageId = file.replace('.skip.json', '')
        // Use the permanent path map populated on first scan. Falls
        // back to a full scan if the map is empty (cold start).
        let meta = this.imagePathMap.get(imageId)
        if (!meta) {
          // Warm the map by triggering a full list once.
          await this.getImageList(true)
          meta = this.imagePathMap.get(imageId)
        }
        if (!meta) continue   // orphan .skip.json — source image vanished
        let reason: string | undefined
        let flaggedAt: string | undefined
        try {
          const raw = await fs.readFile(path.join(this.annotationsPath, file), 'utf-8')
          const parsed = JSON.parse(raw) as { reason?: string; flaggedAt?: string }
          reason = parsed.reason
          flaggedAt = parsed.flaggedAt
        } catch {
          // Malformed — we still list the image, just without reason.
        }
        out.push({
          imageId,
          imagePath: meta.imagePath,
          faction: meta.faction,
          source: meta.source,
          isAnnotated: await this.isImageAnnotated(imageId),
          reason,
          flaggedAt,
        })
      }
    } catch {
      // annotations dir missing
    }
    this.flaggedListCache = out
    return out
  }

  /**
   * Get count of flagged images (total and per faction)
   */
  async getFlaggedCount(): Promise<{ total: number; byFaction: Record<string, number> }> {
    const byFaction: Record<string, number> = {}
    let total = 0
    try {
      const files = await fs.readdir(this.annotationsPath)
      for (const file of files) {
        if (!file.endsWith('.skip.json')) continue
        total++
        // Extract faction from the imageId (format: faction_source_filename)
        const imageId = file.replace('.skip.json', '')
        const parts = imageId.split('_')
        // Faction can be multi-word (e.g. chaos_space_marines_reddit_img1)
        // We need to find the source separator (reddit or dakkadakka)
        const redditIdx = parts.indexOf('reddit')
        const dakkaIdx = parts.indexOf('dakkadakka')
        const sepIdx = redditIdx >= 0 ? redditIdx : dakkaIdx
        if (sepIdx > 0) {
          const faction = remapExportLabel(parts.slice(0, sepIdx).join('_'))
          byFaction[faction] = (byFaction[faction] || 0) + 1
        }
      }
    } catch {
      // annotations dir doesn't exist yet
    }
    return { total, byFaction }
  }

  /**
   * Get annotation progress statistics
   * Shows progress toward the per-faction limit (110 per faction)
   */
  async getProgress(): Promise<AnnotationProgress> {
    const allImages = await this.getImageList(true)
    const annotatedImages = allImages.filter(img => img.isAnnotated)
    // Grab pending, legacy, and flagged buckets from their cached lists
    // so we can surface per-faction counts in the dashboard without
    // re-walking the filesystem three times.
    const [pendingList, legacyList, flaggedList] = await Promise.all([
      this.getPendingImageList(),
      this.getLegacyImageList(),
      this.getFlaggedImageList(),
    ])
    const pendingIds = new Set(pendingList.map(i => i.imageId))
    const legacyIds  = new Set(legacyList.map(i => i.imageId))

    const byFaction: Record<string, { total: number; annotated: number; pending: number; legacy: number; flagged: number }> = {}

    for (const img of allImages) {
      const key = remapExportLabel(img.faction)
      if (!byFaction[key]) {
        byFaction[key] = { total: 0, annotated: 0, pending: 0, legacy: 0, flagged: 0 }
      }
      byFaction[key].total++
      if (img.isAnnotated) byFaction[key].annotated++
      if (pendingIds.has(img.imageId)) byFaction[key].pending++
      if (legacyIds.has(img.imageId))  byFaction[key].legacy++
    }
    // `allImages` is filtered by flagged at list-build time (the main
    // getImageList skips `.skip.json`-flagged entries entirely). Walk
    // the flagged list separately so the per-faction `flagged` count is
    // accurate — otherwise the UI pill would always read 0.
    for (const img of flaggedList) {
      const key = remapExportLabel(img.faction)
      if (!byFaction[key]) {
        byFaction[key] = { total: 0, annotated: 0, pending: 0, legacy: 0, flagged: 0 }
      }
      byFaction[key].flagged++
    }

    // Calculate total target using per-faction caps
    const totalTarget = Object.keys(byFaction).reduce(
      (sum, faction) => sum + this.getFactionLimit(faction), 0
    )

    return {
      totalImages: totalTarget,  // Show target, not raw count
      annotatedImages: annotatedImages.length,
      percentComplete: (annotatedImages.length / totalTarget) * 100,
      pendingImages: pendingList.length,
      legacyImages: legacyList.length,
      flaggedImages: flaggedList.length,
      byFaction,
    }
  }

  /**
   * Generate unique image ID from path
   */
  private getImageId(imagePath: string): string {
    // Use relative path from training_data as ID
    const relativePath = path.relative(this.trainingDataPath, imagePath)
    return relativePath.replace(/[\/\\]/g, '_').replace(/\.[^.]+$/, '')
  }

  /**
   * Get annotation file path for an image ID
   */
  private getAnnotationPath(imageId: string): string {
    // New ebay (training_data_v2) images go in an ebay/ subfolder
    const subfolder = imageId.includes('_ebay_') ? 'ebay' : ''
    return subfolder
      ? path.join(this.annotationsPath, subfolder, `${imageId}.json`)
      : path.join(this.annotationsPath, `${imageId}.json`)
  }

  /**
   * Get random annotated sample images for a faction (for consistency audit)
   */
  async getSampleImages(faction: string, count: number = 9): Promise<Array<{
    imageId: string
    imageBase64: string
    width: number
    height: number
    annotations: BboxAnnotationData[]
  }>> {
    const images = await this.getImageList(true)
    const annotated = images.filter(img => img.faction === faction && img.isAnnotated)

    // Shuffle and take N
    const shuffled = [...annotated].sort(() => Math.random() - 0.5).slice(0, count)
    const results = []

    for (const img of shuffled) {
      try {
        const annotation = await this.getAnnotation(img.imageId)
        if (!annotation || annotation.annotations.length === 0) continue

        const imageBuffer = await fs.readFile(img.imagePath)
        const sharpModule = await import('sharp')
        const metadata = await sharpModule.default(img.imagePath).metadata()

        results.push({
          imageId: img.imageId,
          imageBase64: `data:image/jpeg;base64,${imageBuffer.toString('base64')}`,
          width: metadata.width || 0,
          height: metadata.height || 0,
          annotations: annotation.annotations
        })
      } catch {
        continue
      }
    }

    return results
  }

  /**
   * Export annotations to YOLO format
   * Creates train/val split and converts to YOLO-pose format
   */
  async exportToYOLO(outputPath: string, trainSplit: number = 0.8, options?: { balanced?: boolean; balancedCap?: number }): Promise<{
    trainImages: number
    valImages: number
    classesFile: string
  }> {
    logger.info('🔄 Exporting annotations to YOLO format...')

    // Get all annotated images
    const images = await this.getImageList(true)
    const annotatedImages = images.filter(img => img.isAnnotated)

    if (annotatedImages.length === 0) {
      throw new Error('No annotated images found')
    }

    // Create output directories
    const imagesTrainDir = path.join(outputPath, 'images', 'train')
    const imagesValDir = path.join(outputPath, 'images', 'val')
    const labelsTrainDir = path.join(outputPath, 'labels', 'train')
    const labelsValDir = path.join(outputPath, 'labels', 'val')

    await fs.mkdir(imagesTrainDir, { recursive: true })
    await fs.mkdir(imagesValDir, { recursive: true })
    await fs.mkdir(labelsTrainDir, { recursive: true })
    await fs.mkdir(labelsValDir, { recursive: true })

    // Collect all unique classes
    const classesSet = new Set<string>()
    let annotations: Array<{ image: typeof annotatedImages[0]; annotation: ImageAnnotation }> = []

    for (const img of annotatedImages) {
      const annotation = await this.getAnnotation(img.imageId)
      // Only include images with actual annotations (skip empty/skipped ones)
      if (annotation && annotation.annotations.length > 0) {
        annotations.push({ image: img, annotation })
        annotation.annotations.forEach(ann => classesSet.add(remapExportLabel(ann.classLabel)))
      }
    }

    // Balanced export: cap each faction at the minimum faction count (or custom cap)
    if (options?.balanced) {
      const byFaction = new Map<string, typeof annotations>()
      for (const entry of annotations) {
        const faction = entry.image.faction
        const existing = byFaction.get(faction) || []
        existing.push(entry)
        byFaction.set(faction, existing)
      }

      const minCount = options.balancedCap || Math.min(...Array.from(byFaction.values()).map(v => v.length))
      logger.info(`⚖️  Balanced export: capping each faction at ${minCount} images`)

      const balanced: typeof annotations = []
      for (const [faction, entries] of byFaction) {
        const shuffled = [...entries].sort(() => Math.random() - 0.5)
        const capped = shuffled.slice(0, minCount)
        balanced.push(...capped)
        logger.info(`   ${faction}: ${capped.length}/${entries.length}`)
      }
      annotations = balanced
    }

    logger.info(`📊 Exporting ${annotations.length} images with annotations (excluded ${annotatedImages.length - annotations.length} skipped/empty)`)

    // Create class mapping
    const classes = Array.from(classesSet).sort()
    const classToIndex = new Map(classes.map((cls, idx) => [cls, idx]))

    // Split train/val
    const shuffled = [...annotations].sort(() => Math.random() - 0.5)
    const trainCount = Math.floor(shuffled.length * trainSplit)
    const trainSet = shuffled.slice(0, trainCount)
    const valSet = shuffled.slice(trainCount)

    // Process train set
    for (const { image, annotation } of trainSet) {
      await this.exportImageAndLabel(
        image.imagePath,
        annotation,
        imagesTrainDir,
        labelsTrainDir,
        classToIndex,
        annotation.width,
        annotation.height
      )
    }

    // Process val set
    for (const { image, annotation } of valSet) {
      await this.exportImageAndLabel(
        image.imagePath,
        annotation,
        imagesValDir,
        labelsValDir,
        classToIndex,
        annotation.width,
        annotation.height
      )
    }

    // Write classes file
    const classesFile = path.join(outputPath, 'classes.txt')
    await fs.writeFile(classesFile, classes.join('\n'), 'utf-8')

    // Write YOLO data.yaml
    const yamlContent = `# YOLO Dataset Configuration
path: ${outputPath}
train: images/train
val: images/val

# Classes
nc: ${classes.length}
names: [${classes.map(c => `"${c}"`).join(', ')}]
`
    await fs.writeFile(path.join(outputPath, 'data.yaml'), yamlContent, 'utf-8')

    logger.info(`✅ YOLO export complete:`)
    logger.info(`   Train: ${trainSet.length} images`)
    logger.info(`   Val: ${valSet.length} images`)
    logger.info(`   Classes: ${classes.length}`)

    return {
      trainImages: trainSet.length,
      valImages: valSet.length,
      classesFile
    }
  }

  /**
   * Export single image and label to YOLO format
   */
  private async exportImageAndLabel(
    imagePath: string,
    annotation: ImageAnnotation,
    imagesDir: string,
    labelsDir: string,
    classToIndex: Map<string, number>,
    imageWidth: number,
    imageHeight: number
  ): Promise<void> {
    const imageName = path.basename(imagePath)
    const labelName = imageName.replace(/\.[^.]+$/, '.txt')

    // Copy image
    const destImagePath = path.join(imagesDir, imageName)
    await fs.copyFile(imagePath, destImagePath)

    // Convert annotations to YOLO format
    const yoloLines: string[] = []

    for (const ann of annotation.annotations) {
      const classIndex = classToIndex.get(remapExportLabel(ann.classLabel))
      if (classIndex === undefined) continue

      // Normalize bbox to [0, 1]
      // YOLO format: class x_center y_center width height
      const x_center = (ann.modelBbox.x + ann.modelBbox.width / 2) / imageWidth
      const y_center = (ann.modelBbox.y + ann.modelBbox.height / 2) / imageHeight
      const width = ann.modelBbox.width / imageWidth
      const height = ann.modelBbox.height / imageHeight

      const line = [
        classIndex,
        x_center.toFixed(6),
        y_center.toFixed(6),
        width.toFixed(6),
        height.toFixed(6)
      ].join(' ')

      yoloLines.push(line)
    }

    // Write label file
    const destLabelPath = path.join(labelsDir, labelName)
    await fs.writeFile(destLabelPath, yoloLines.join('\n'), 'utf-8')
  }
}

// Singleton instance
export const annotationService = new AnnotationService()
