import { openDB, type DBSchema, type IDBPDatabase } from 'idb'
import type { ScanResult } from '../types/detection'
import type { Army } from '../types/army'

interface BattleScannerDB extends DBSchema {
  scans: {
    key: string
    value: ScanResult
    indexes: { 'by-timestamp': string }
  }
  armies: {
    key: string
    value: Army
    indexes: { 'by-updated': string }
  }
}

let dbPromise: Promise<IDBPDatabase<BattleScannerDB>> | null = null

function getDb() {
  if (!dbPromise) {
    dbPromise = openDB<BattleScannerDB>('battle-scanner', 1, {
      upgrade(db) {
        const scanStore = db.createObjectStore('scans', { keyPath: 'id' })
        scanStore.createIndex('by-timestamp', 'timestamp')

        const armyStore = db.createObjectStore('armies', { keyPath: 'id' })
        armyStore.createIndex('by-updated', 'updatedAt')
      },
    })
  }
  return dbPromise
}

// Scans
export async function saveScan(scan: ScanResult): Promise<void> {
  const db = await getDb()
  await db.put('scans', scan)
}

export async function getScan(id: string): Promise<ScanResult | undefined> {
  const db = await getDb()
  return db.get('scans', id)
}

export async function getAllScans(): Promise<ScanResult[]> {
  const db = await getDb()
  const all = await db.getAllFromIndex('scans', 'by-timestamp')
  return all.reverse()
}

export async function deleteScan(id: string): Promise<void> {
  const db = await getDb()
  await db.delete('scans', id)
}

// Armies
export async function saveArmy(army: Army): Promise<void> {
  const db = await getDb()
  await db.put('armies', army)
}

export async function getArmy(id: string): Promise<Army | undefined> {
  const db = await getDb()
  return db.get('armies', id)
}

export async function getAllArmies(): Promise<Army[]> {
  const db = await getDb()
  const all = await db.getAllFromIndex('armies', 'by-updated')
  return all.reverse()
}

export async function deleteArmy(id: string): Promise<void> {
  const db = await getDb()
  await db.delete('armies', id)
}
