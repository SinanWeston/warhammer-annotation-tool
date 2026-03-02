import { openDB, type IDBPDatabase } from 'idb'
import { generateId } from './id'
import type { DetectionResult } from '../types/detection'

export interface StoredScan {
  id: string
  timestamp: string
  imageDataUrl: string
  results: DetectionResult
}

export interface StoredFeedback {
  id: string
  scanId: string
  originalFaction: string
  correctedFaction: string | null // null = "not a miniature"
  detectionIndex: number
  timestamp: string
  synced: 0 | 1
}

const DB_NAME = 'battle-scanner'
const DB_VERSION = 1

let dbPromise: Promise<IDBPDatabase> | null = null

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('scans')) {
          const scanStore = db.createObjectStore('scans', { keyPath: 'id' })
          scanStore.createIndex('timestamp', 'timestamp')
        }
        if (!db.objectStoreNames.contains('feedback')) {
          const feedbackStore = db.createObjectStore('feedback', { keyPath: 'id' })
          feedbackStore.createIndex('synced', 'synced')
          feedbackStore.createIndex('scanId', 'scanId')
        }
      },
      terminated() {
        dbPromise = null
      }
    })
  }
  return dbPromise
}

export async function saveScan(imageDataUrl: string, results: DetectionResult): Promise<StoredScan> {
  const db = await getDB()
  const scan: StoredScan = {
    id: generateId(),
    timestamp: new Date().toISOString(),
    imageDataUrl,
    results,
  }
  await db.put('scans', scan)
  return scan
}

export async function getAllScans(): Promise<StoredScan[]> {
  const db = await getDB()
  const scans = await db.getAllFromIndex('scans', 'timestamp')
  return scans.reverse() // newest first
}

export async function getScan(id: string): Promise<StoredScan | undefined> {
  const db = await getDB()
  return db.get('scans', id)
}

export async function clearAllScans(): Promise<void> {
  const db = await getDB()
  await db.clear('scans')
}

export async function saveFeedback(
  scanId: string,
  originalFaction: string,
  correctedFaction: string | null,
  detectionIndex: number
): Promise<StoredFeedback> {
  const db = await getDB()
  const feedback: StoredFeedback = {
    id: generateId(),
    scanId,
    originalFaction,
    correctedFaction,
    detectionIndex,
    timestamp: new Date().toISOString(),
    synced: 0,
  }
  await db.put('feedback', feedback)
  return feedback
}

export async function getUnsyncedFeedback(): Promise<StoredFeedback[]> {
  const db = await getDB()
  return db.getAllFromIndex('feedback', 'synced', 0)
}

export async function markFeedbackSynced(ids: string[]): Promise<void> {
  const db = await getDB()
  const tx = db.transaction('feedback', 'readwrite')
  for (const id of ids) {
    const feedback = await tx.store.get(id)
    if (feedback) {
      feedback.synced = 1
      await tx.store.put(feedback)
    }
  }
  await tx.done
}
