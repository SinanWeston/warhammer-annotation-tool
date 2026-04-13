import type { ScanResult } from '../types/detection'

/**
 * Hardcoded mock scan result demonstrating a mixed Space Marines + Necrons battle.
 * Bboxes are in pixel coordinates for a 1200x900 image.
 */
export const MOCK_SCAN_RESULT: Omit<ScanResult, 'id' | 'timestamp' | 'imageDataUrl'> = {
  imageWidth: 1200,
  imageHeight: 900,
  factionHint: undefined,
  detections: [
    // Space Marines — high confidence
    { id: 'det-01', faction: 'space_marines', unitName: 'Captain', confidence: 0.96, bbox: { x: 100, y: 120, width: 80, height: 120 }, points: 80, role: 'hq' },
    { id: 'det-02', faction: 'space_marines', unitName: 'Intercessors', confidence: 0.93, bbox: { x: 200, y: 200, width: 160, height: 100 }, points: 90, role: 'troops' },
    { id: 'det-03', faction: 'space_marines', unitName: 'Intercessors', confidence: 0.91, bbox: { x: 380, y: 210, width: 150, height: 95 }, points: 90, role: 'troops' },
    { id: 'det-04', faction: 'space_marines', unitName: 'Redemptor Dreadnought', confidence: 0.89, bbox: { x: 550, y: 100, width: 120, height: 180 }, points: 195, role: 'elites' },
    { id: 'det-05', faction: 'space_marines', unitName: 'Eradicator Squad', confidence: 0.85, bbox: { x: 720, y: 250, width: 110, height: 90 }, points: 120, role: 'heavy_support' },
    { id: 'det-06', faction: 'space_marines', unitName: 'Bladeguard Veterans', confidence: 0.82, bbox: { x: 50, y: 380, width: 130, height: 100 }, points: 105, role: 'elites' },

    // Necrons — mixed confidence
    { id: 'det-07', faction: 'necrons', unitName: 'Overlord', confidence: 0.94, bbox: { x: 850, y: 150, width: 70, height: 110 }, points: 85, role: 'hq' },
    { id: 'det-08', faction: 'necrons', unitName: 'Necron Warriors', confidence: 0.88, bbox: { x: 900, y: 350, width: 200, height: 120 }, points: 110, role: 'troops' },
    { id: 'det-09', faction: 'necrons', unitName: 'Skorpekh Destroyers', confidence: 0.79, bbox: { x: 750, y: 500, width: 140, height: 110 }, points: 90, role: 'elites' },
    { id: 'det-10', faction: 'necrons', unitName: 'Canoptek Wraiths', confidence: 0.72, bbox: { x: 500, y: 550, width: 160, height: 100 }, points: 105, role: 'fast_attack' },

    // Low confidence — uncertain
    { id: 'det-11', faction: 'space_marines', unitName: 'Scouts', confidence: 0.42, bbox: { x: 300, y: 700, width: 100, height: 80 }, points: 60, role: 'troops' },
    { id: 'det-12', faction: 'necrons', unitName: 'Canoptek Scarab Swarms', confidence: 0.35, bbox: { x: 600, y: 750, width: 90, height: 60 }, points: 36, role: 'fast_attack' },
  ],
}

/** Placeholder image — a 1200x900 dark gray rectangle with "SAMPLE SCAN" text */
export function generatePlaceholderImage(): string {
  const canvas = document.createElement('canvas')
  canvas.width = 1200
  canvas.height = 900
  const ctx = canvas.getContext('2d')!
  // Background
  ctx.fillStyle = '#1a1a2e'
  ctx.fillRect(0, 0, 1200, 900)
  // Grid pattern
  ctx.strokeStyle = '#2a2a4e'
  ctx.lineWidth = 1
  for (let x = 0; x < 1200; x += 60) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 900); ctx.stroke()
  }
  for (let y = 0; y < 900; y += 60) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(1200, y); ctx.stroke()
  }
  // Title
  ctx.fillStyle = '#b08d57'
  ctx.font = '700 36px Cinzel, serif'
  ctx.textAlign = 'center'
  ctx.fillText('SAMPLE BATTLE SCAN', 600, 440)
  ctx.font = '16px Orbitron, monospace'
  ctx.fillStyle = '#5a6b82'
  ctx.fillText('Space Marines vs Necrons — Mock Data', 600, 480)
  return canvas.toDataURL('image/jpeg', 0.85)
}
