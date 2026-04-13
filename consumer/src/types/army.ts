export interface ArmyUnit {
  id: string
  unitName: string
  faction: string
  role: string
  count: number
  pointsPerModel: number
  sourceDetectionId?: string
}

export interface Army {
  id: string
  name: string
  units: ArmyUnit[]
  createdAt: string
  updatedAt: string
  sourceScanIds: string[]
  pointsLimit: number
}

export type PlaystyleTag = 'aggressive' | 'defensive' | 'balanced' | 'competitive'

export interface ArmySuggestion {
  id: string
  title: string
  description: string
  playstyle: PlaystyleTag
  faction: string
  suggestedUnits: { unitName: string; count: number; reason: string }[]
  totalPoints: number
}
