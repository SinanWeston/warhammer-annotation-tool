import JSZip from 'jszip'
import { saveImage } from './db'
import type { BatchManifest, PredictionBox, StoredImage } from '../types'

export async function importZip(
  file: File,
  onProgress?: (loaded: number, total: number) => void
): Promise<number> {
  const zip = await JSZip.loadAsync(file)

  // Read manifest
  const manifestFile = zip.file('manifest.json')
  if (!manifestFile) {
    throw new Error('Invalid batch zip: missing manifest.json')
  }
  const manifest: BatchManifest = JSON.parse(await manifestFile.async('text'))

  // Read predictions (optional)
  let predictionsMap: Record<string, PredictionBox[]> = {}
  const predictionsFile = zip.file('predictions.json')
  if (predictionsFile) {
    predictionsMap = JSON.parse(await predictionsFile.async('text'))
  }

  const total = manifest.images.length
  let loaded = 0

  for (const entry of manifest.images) {
    const imageFile = zip.file(entry.filename)
    if (!imageFile) continue

    const blob = await imageFile.async('blob')

    const storedImage: StoredImage = {
      imageId: entry.imageId,
      faction: entry.faction,
      blob,
      width: entry.width,
      height: entry.height,
      predictions: predictionsMap[entry.imageId]
    }

    // Retry once on DB connection errors (iOS Safari can close the connection mid-import)
    try {
      await saveImage(storedImage)
    } catch {
      await new Promise(r => setTimeout(r, 300))
      await saveImage(storedImage)
    }
    loaded++
    onProgress?.(loaded, total)
  }

  return loaded
}
