// Dataset Annotation Types

export interface BboxAnnotation {
  id: string  // Unique ID for this annotation
  x: number  // Top-left X (pixels) - model bbox
  y: number  // Top-left Y (pixels)
  width: number  // Width (pixels)
  height: number  // Height (pixels)
  classLabel: string  // Faction name (e.g., "tyranids", "space_marines")
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
