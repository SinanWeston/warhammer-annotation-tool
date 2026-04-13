import { create } from 'zustand'
import type { Army, ArmyUnit } from '../types/army'
import type { Detection } from '../types/detection'
import { generateId } from '../lib/id'
import { saveArmy } from '../services/storageService'

interface ArmyState {
  currentArmy: Army
  resetArmy: () => void
  loadArmy: (army: Army) => void
  setArmyName: (name: string) => void
  setPointsLimit: (limit: number) => void
  addUnitsFromDetections: (detections: Detection[], scanId: string) => void
  addUnit: (unit: Omit<ArmyUnit, 'id'>) => void
  removeUnit: (id: string) => void
  updateUnitCount: (id: string, delta: number) => void
  saveCurrentArmy: () => Promise<void>
}

function createEmptyArmy(): Army {
  return {
    id: generateId(),
    name: 'New Army',
    units: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    sourceScanIds: [],
    pointsLimit: 2000,
  }
}

export const useArmyStore = create<ArmyState>((set, get) => ({
  currentArmy: createEmptyArmy(),

  resetArmy: () => set({ currentArmy: createEmptyArmy() }),

  loadArmy: (army) => set({ currentArmy: army }),

  setArmyName: (name) => {
    set(s => ({
      currentArmy: { ...s.currentArmy, name, updatedAt: new Date().toISOString() },
    }))
  },

  setPointsLimit: (limit) => {
    set(s => ({
      currentArmy: { ...s.currentArmy, pointsLimit: limit, updatedAt: new Date().toISOString() },
    }))
  },

  addUnitsFromDetections: (detections, scanId) => {
    const newUnits: ArmyUnit[] = detections
      .filter(d => d.confidence >= 0.5) // Only add confident detections
      .map(d => ({
        id: generateId(),
        unitName: d.unitName,
        faction: d.faction,
        role: d.role,
        count: 1,
        pointsPerModel: d.points,
        sourceDetectionId: d.id,
      }))

    set(s => ({
      currentArmy: {
        ...s.currentArmy,
        units: [...s.currentArmy.units, ...newUnits],
        sourceScanIds: [...new Set([...s.currentArmy.sourceScanIds, scanId])],
        updatedAt: new Date().toISOString(),
      },
    }))
  },

  addUnit: (unit) => {
    const armyUnit: ArmyUnit = { ...unit, id: generateId() }
    set(s => ({
      currentArmy: {
        ...s.currentArmy,
        units: [...s.currentArmy.units, armyUnit],
        updatedAt: new Date().toISOString(),
      },
    }))
  },

  removeUnit: (id) => {
    set(s => ({
      currentArmy: {
        ...s.currentArmy,
        units: s.currentArmy.units.filter(u => u.id !== id),
        updatedAt: new Date().toISOString(),
      },
    }))
  },

  updateUnitCount: (id, delta) => {
    set(s => ({
      currentArmy: {
        ...s.currentArmy,
        units: s.currentArmy.units.map(u =>
          u.id === id ? { ...u, count: Math.max(0, u.count + delta) } : u
        ).filter(u => u.count > 0),
        updatedAt: new Date().toISOString(),
      },
    }))
  },

  saveCurrentArmy: async () => {
    const army = get().currentArmy
    await saveArmy(army)
  },
}))
