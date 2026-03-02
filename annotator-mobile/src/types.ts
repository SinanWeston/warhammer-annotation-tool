export interface MobileBbox {
  id: string
  x: number
  y: number
  width: number
  height: number
  classLabel: string
  fromPrediction: boolean
  confidence?: number
}

export interface MobileAnnotation {
  id: string
  imageId: string
  imageWidth: number
  imageHeight: number
  bboxes: MobileBbox[]
  completed: boolean
  skipped?: boolean
  syncedAt: string | null
  updatedAt: string
}

export interface PredictionBox {
  x: number
  y: number
  width: number
  height: number
  classLabel: string
  confidence: number
}

export interface StoredImage {
  imageId: string
  faction: string
  blob: Blob
  width: number
  height: number
  predictions?: PredictionBox[]
}

export interface BatchManifest {
  images: Array<{
    imageId: string
    faction: string
    filename: string
    width: number
    height: number
  }>
  exportedAt: string
}

export interface SyncResult {
  synced: number
  skipped: number
  errors: string[]
}
