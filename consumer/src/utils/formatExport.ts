import type { Army } from '../types/army'
import { getFactionDisplayName } from './factions'

export function armyToShareHash(army: Army): string {
  const compact = {
    n: army.name,
    l: army.pointsLimit,
    u: army.units.map(u => ({
      n: u.unitName,
      f: u.faction,
      c: u.count,
      p: u.pointsPerModel,
      r: u.role,
    })),
  }
  return btoa(JSON.stringify(compact))
}

export function armyFromShareHash(hash: string): Partial<Army> | null {
  try {
    const compact = JSON.parse(atob(hash))
    return {
      name: compact.n,
      pointsLimit: compact.l,
      units: compact.u.map((u: { n: string; f: string; c: number; p: number; r: string }, i: number) => ({
        id: `shared-${i}`,
        unitName: u.n,
        faction: u.f,
        count: u.c,
        pointsPerModel: u.p,
        role: u.r,
      })),
    }
  } catch {
    return null
  }
}
