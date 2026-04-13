import { create } from 'zustand'
import type { ScanResult } from '../types/detection'
import type { Army } from '../types/army'
import * as storage from '../services/storageService'

interface HistoryState {
  scans: ScanResult[]
  armies: Army[]
  isLoading: boolean
  loadHistory: () => Promise<void>
  removeScan: (id: string) => Promise<void>
  removeArmy: (id: string) => Promise<void>
}

export const useHistoryStore = create<HistoryState>((set) => ({
  scans: [],
  armies: [],
  isLoading: false,

  loadHistory: async () => {
    set({ isLoading: true })
    const [scans, armies] = await Promise.all([
      storage.getAllScans(),
      storage.getAllArmies(),
    ])
    set({ scans, armies, isLoading: false })
  },

  removeScan: async (id) => {
    await storage.deleteScan(id)
    set(s => ({ scans: s.scans.filter(scan => scan.id !== id) }))
  },

  removeArmy: async (id) => {
    await storage.deleteArmy(id)
    set(s => ({ armies: s.armies.filter(army => army.id !== id) }))
  },
}))
