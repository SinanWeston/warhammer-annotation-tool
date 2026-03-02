import { getPendingSync, markSynced } from './db'
import type { SyncResult } from '../types'

function getApiBase() {
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('backendUrl') : null
  return `${stored || import.meta.env.VITE_BACKEND_URL || ''}/api/mobile`
}
const BATCH_SIZE = 25

export async function syncAnnotations(
  onProgress?: (done: number, total: number) => void
): Promise<SyncResult> {
  const pending = await getPendingSync()
  if (pending.length === 0) {
    return { synced: 0, skipped: 0, errors: [] }
  }

  let totalSynced = 0
  let totalSkipped = 0
  const allErrors: string[] = []

  // Chunk into batches to avoid timeout / payload size issues
  for (let i = 0; i < pending.length; i += BATCH_SIZE) {
    const batch = pending.slice(i, i + BATCH_SIZE)

    const response = await fetch(`${getApiBase()}/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ annotations: batch }),
    })

    if (!response.ok) {
      allErrors.push(`Batch ${Math.floor(i / BATCH_SIZE) + 1} failed: ${response.status}`)
      continue
    }

    const result = await response.json()
    const data = result.data

    totalSynced += data.synced || 0
    totalSkipped += data.skipped || 0
    if (data.errors) allErrors.push(...data.errors)

    // Mark synced + skipped as done (backend already has them)
    const doneIds = [
      ...(data.syncedIds || []),
      ...(data.skippedIds || []),
    ]
    if (doneIds.length > 0) {
      await markSynced(doneIds)
    }
    // failedIds are NOT marked — they'll retry next sync

    onProgress?.(Math.min(i + BATCH_SIZE, pending.length), pending.length)
  }

  return { synced: totalSynced, skipped: totalSkipped, errors: allErrors }
}

export async function downloadBatch(
  faction?: string,
  limit: number = 500,
  includePredictions: boolean = true
): Promise<Blob> {
  const response = await fetch(`${getApiBase()}/export-batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ faction, limit, includePredictions }),
  })

  if (!response.ok) {
    throw new Error(`Download failed: ${response.status} ${response.statusText}`)
  }

  return response.blob()
}

export function getOnlineStatus(): boolean {
  return navigator.onLine
}

export function onOnlineStatusChange(cb: (online: boolean) => void): () => void {
  const handleOnline = () => cb(true)
  const handleOffline = () => cb(false)
  window.addEventListener('online', handleOnline)
  window.addEventListener('offline', handleOffline)
  return () => {
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
  }
}
