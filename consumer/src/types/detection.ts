export interface Detection {
  faction: string
  confidence: number
  bbox: { x: number; y: number; width: number; height: number }
}

export interface FactionSummary {
  faction: string
  count: number
  avgConfidence: number
  color: string
}

export interface DetectionResult {
  imageWidth: number
  imageHeight: number
  detections: Detection[]
  summary: FactionSummary[]
  totalDetected: number
  inferenceTimeMs: number
}

export interface AccumulatedArmy {
  scanIds: string[]
  factions: { faction: string; count: number; color: string }[]
  totalModels: number
}
