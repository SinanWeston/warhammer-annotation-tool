// Dashboard Stats Types

export interface BoxSizeStats {
  avgWidth: number
  avgHeight: number
  avgAreaRatio: number // box area / image area
}

export interface OutlierEntry {
  imageId: string
  faction: string
  reason: 'tiny_box' | 'huge_box' | 'too_many_boxes'
  details: string
  boxCount?: number
  areaRatio?: number
}

export interface DashboardStats {
  boxesPerImage: {
    min: number
    max: number
    avg: number
    median: number
    distribution: Record<string, number> // bucket label -> count
  }
  boxSizesByFaction: Record<string, BoxSizeStats>
  annotationSpeed: {
    perDay: Record<string, number> // date string -> count
  }
  outliers: OutlierEntry[]
  totalAnnotations: number
  totalBoxes: number
}

export interface ActiveLearningStatus {
  running: boolean
  processed: number
  total: number
  totalScored: number
}
