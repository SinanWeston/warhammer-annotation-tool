export interface BBox {
  x: number
  y: number
  width: number
  height: number
}

export interface Detection {
  id: string
  faction: string
  unitName: string
  confidence: number
  bbox: BBox
  points: number
  role: string
}

export type GroupingMode = 'faction' | 'role' | 'flat'

export interface ScanResult {
  id: string
  timestamp: string
  imageDataUrl: string
  imageWidth: number
  imageHeight: number
  detections: Detection[]
  factionHint?: string
}

export interface FactionSummary {
  faction: string
  count: number
  avgConfidence: number
  totalPoints: number
  color: string
}
