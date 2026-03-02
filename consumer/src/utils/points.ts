import { getPointsPerModel } from './factions'
import type { DetectionResult } from '../types/detection'

export function estimateFactionPoints(factionKey: string, count: number): number {
  return getPointsPerModel(factionKey) * count
}

export function estimateTotalPoints(results: DetectionResult): number {
  return results.summary.reduce(
    (total, s) => total + estimateFactionPoints(s.faction, s.count),
    0
  )
}
