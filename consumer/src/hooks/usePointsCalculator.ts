import { useMemo } from 'react'
import type { ArmyUnit } from '../types/army'

export function usePointsCalculator(units: ArmyUnit[], pointsLimit: number) {
  return useMemo(() => {
    const totalPoints = units.reduce((sum, u) => sum + u.count * u.pointsPerModel, 0)
    const totalModels = units.reduce((sum, u) => sum + u.count, 0)
    const percentage = pointsLimit > 0 ? Math.min(100, (totalPoints / pointsLimit) * 100) : 0
    const isOver = totalPoints > pointsLimit
    const remaining = pointsLimit - totalPoints

    return { totalPoints, totalModels, percentage, isOver, remaining }
  }, [units, pointsLimit])
}
