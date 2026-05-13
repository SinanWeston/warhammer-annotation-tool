// Dataset Annotation Types

export interface BboxAnnotation {
  id: string  // Unique ID for this annotation
  x: number  // Top-left X (pixels) - model bbox
  y: number  // Top-left Y (pixels)
  width: number  // Width (pixels)
  height: number  // Height (pixels)
  classLabel: string  // Faction slug (e.g., "tyranids", "space_marines").
                       // Legacy name — semantically always a faction;
                       // feeds YOLO export unchanged.
  unit_slug?: string   // Optional: canonical unit slug within the
                       // faction (e.g., "intercessors"). Empty = "I
                       // know the faction but haven't identified the
                       // unit yet". Picker is scoped to classLabel.
  baseBbox?: {  // Optional base bbox (inner bbox for the miniature's base)
    x: number
    y: number
    width: number
    height: number
  }
  // AI prediction fields
  confidence?: number  // AI confidence score (0-1)
  isPrediction?: boolean  // True if this is an AI prediction (pending validation)
  isAccepted?: boolean   // True if user marked this prediction as correct (stays on canvas, turns green)
  validated?: boolean  // True if user has validated this prediction
  // Validation tracking for training data
  validationAction?: 'accepted' | 'rejected' | 'redrawn'  // What action user took
  originalPrediction?: boolean  // Was this originally an AI prediction?
}

/** Response of `GET /api/annotate/taxonomy`. The frontend fetches this
 *  once on mount of the annotation interface and drives the per-bbox
 *  faction + unit dropdowns from it, plus the source picker. */
export interface Taxonomy {
  factions: string[]
  unitsByFaction: Record<string, Array<{ slug: string; name: string; category?: string }>>
  sources: string[]   // ANNOTATION_SOURCES env, e.g. ["ebay","isolation","cmon"]
}

/** Response of `GET /api/annotate/progress`. Mirrors the backend's
 *  `AnnotationProgress` interface in annotationService.ts — keep the
 *  two in sync. */
export interface AnnotationProgress {
  totalImages: number
  annotatedImages: number
  percentComplete: number
  pendingImages: number
  legacyImages: number
  byFaction: Record<string, { total: number; annotated: number; pending: number; legacy: number }>
}

/** Validation error/warning surface from /save responses + the
 *  quality-issues modal. Mirrors backend's QualityIssue. */
export interface QualityIssue {
  type: 'error' | 'warning'
  code: string
  message: string
  bboxId?: string
}

/** Image payload returned by /api/annotate/{next,image/:id}. The
 *  `imageBase64` and dimensions only land once the route has read the
 *  file off disk; the basic identity (imageId, paths, faction, source)
 *  is always present. NB: not named `ImageData` to avoid shadowing the
 *  DOM's built-in ImageData. */
export interface AnnotatorImage {
  imageId: string
  imagePath: string
  faction: string
  source: string
  imageBase64?: string
  width?: number
  height?: number
  /** Provenance: always has filename. CMON-sourced images also include
   *  the artist's title, score (0–10), vote count, tags, and a link
   *  back to the source page. */
  meta?: {
    filename: string
    title?: string
    artist?: string
    sourceUrl?: string
    score?: number
    votes?: number
    tags?: string[]
  }
  /** Optional active-learning hint — sent when prioritize-by-confidence
   *  mode is on. */
  confidenceScore?: number
  /** gw_walk-only — present only when status=gw_walk. The raw folder name
   *  from the GW shop scrape (e.g. `ael_shining_spear_feature`). Used by
   *  the walkthrough UI as a label hint when the folder isn't mapped to
   *  a canonical unit_slug yet. */
  gwFolderSlug?: string | null
  /** gw_walk-only — canonical unit_slug pre-fill from
   *  `scripts/data/gw_slug_canonical_map.json`. Null/empty = unmapped;
   *  the user picks from the dropdown. */
  suggestedUnitSlug?: string | null
}
