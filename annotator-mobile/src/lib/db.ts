import { openDB, type IDBPDatabase } from 'idb'
import type { StoredImage, MobileAnnotation, MobileBbox } from '../types'
import { generateId } from './id'

const DB_NAME = 'annotator-mobile'
const DB_VERSION = 1

let dbPromise: Promise<IDBPDatabase> | null = null

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('images')) {
          db.createObjectStore('images', { keyPath: 'imageId' })
        }
        if (!db.objectStoreNames.contains('annotations')) {
          const store = db.createObjectStore('annotations', { keyPath: 'imageId' })
          store.createIndex('syncedAt', 'syncedAt')
          store.createIndex('completed', 'completed')
        }
      },
      terminated() {
        // DB was closed unexpectedly (e.g. iOS Safari background eviction)
        // Reset so the next getDB() call opens a fresh connection
        dbPromise = null
      }
    })
  }
  return dbPromise
}

export async function saveImage(image: StoredImage): Promise<void> {
  const db = await getDB()
  await db.put('images', image)
}

export async function getImage(imageId: string): Promise<StoredImage | undefined> {
  const db = await getDB()
  return db.get('images', imageId)
}

export async function getAllImageIds(): Promise<string[]> {
  const db = await getDB()
  return db.getAllKeys('images') as Promise<string[]>
}

export async function getNextUnannotated(): Promise<StoredImage | undefined> {
  const db = await getDB()
  const tx = db.transaction(['images', 'annotations'], 'readonly')
  const imageStore = tx.objectStore('images')
  const annotationStore = tx.objectStore('annotations')

  let cursor = await imageStore.openCursor()
  while (cursor) {
    const annotation = await annotationStore.get(cursor.key)
    if (!annotation || !annotation.completed) {
      return cursor.value as StoredImage
    }
    cursor = await cursor.continue()
  }
  return undefined
}

export async function saveAnnotation(
  imageId: string,
  bboxes: MobileBbox[],
  completed: boolean,
  imageWidth: number,
  imageHeight: number,
  skipped?: boolean
): Promise<void> {
  const db = await getDB()
  const existing = await db.get('annotations', imageId)
  const annotation: MobileAnnotation = {
    id: existing?.id || generateId(),
    imageId,
    imageWidth,
    imageHeight,
    bboxes,
    completed,
    skipped: skipped || false,
    syncedAt: existing?.syncedAt ?? null,
    updatedAt: new Date().toISOString()
  }
  await db.put('annotations', annotation)
}

export async function getAnnotation(imageId: string): Promise<MobileAnnotation | undefined> {
  const db = await getDB()
  return db.get('annotations', imageId)
}

export async function getPendingSync(): Promise<MobileAnnotation[]> {
  const db = await getDB()
  const all = await db.getAll('annotations')
  return all.filter(a => a.completed && !a.syncedAt)
}

export async function markSynced(imageIds: string[]): Promise<void> {
  const db = await getDB()
  const tx = db.transaction('annotations', 'readwrite')
  const now = new Date().toISOString()
  for (const id of imageIds) {
    const annotation = await tx.store.get(id)
    if (annotation) {
      annotation.syncedAt = now
      await tx.store.put(annotation)
    }
  }
  await tx.done
}

export async function getStats(): Promise<{
  totalImages: number
  annotated: number
  pendingSync: number
}> {
  const db = await getDB()
  const totalImages = await db.count('images')
  const allAnnotations = await db.getAll('annotations')
  const annotated = allAnnotations.filter(a => a.completed).length
  const pendingSync = allAnnotations.filter(a => a.completed && !a.syncedAt).length
  return { totalImages, annotated, pendingSync }
}

export async function clearSyncedImages(): Promise<number> {
  const db = await getDB()
  const annotations = await db.getAll('annotations')
  const synced = annotations.filter(a => a.syncedAt)
  const tx = db.transaction(['images', 'annotations'], 'readwrite')
  let cleared = 0
  for (const ann of synced) {
    await tx.objectStore('images').delete(ann.imageId)
    await tx.objectStore('annotations').delete(ann.imageId)
    cleared++
  }
  await tx.done
  return cleared
}
