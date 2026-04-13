import type { ScanResult } from '../types/detection'
import { MOCK_SCAN_RESULT, generatePlaceholderImage } from '../data/mockScan'
import { generateId } from '../lib/id'

/**
 * Single swap point for AI integration.
 * Currently returns mock data. When real inference is ready,
 * only the body of this function changes.
 */
export async function detectFromImages(
  _images: File[],
  _factionHint?: string
): Promise<ScanResult> {
  // Simulate network latency
  await new Promise(r => setTimeout(r, 1500))

  return {
    ...MOCK_SCAN_RESULT,
    id: generateId(),
    timestamp: new Date().toISOString(),
    imageDataUrl: generatePlaceholderImage(),
  }
}
