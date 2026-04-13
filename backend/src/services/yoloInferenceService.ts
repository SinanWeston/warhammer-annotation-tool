/**
 * YOLO Inference Service
 * Runs the trained YOLO model to predict bounding boxes on images
 */

import { spawn } from 'child_process'
import { config } from '../config'
import logger from '../utils/logger'

export interface PredictedBox {
  id: string
  x: number
  y: number
  width: number
  height: number
  classLabel: string
  confidence: number
}

export interface PredictionResult {
  imageId: string
  predictions: PredictedBox[]
  inferenceTime: number
}

/**
 * Run YOLO inference on an image
 */
export async function predictBoxes(imagePath: string, imageId: string): Promise<PredictionResult> {
  const startTime = Date.now()

  return new Promise((resolve, reject) => {
    const pythonScript = `
import sys
import json
from ultralytics import YOLO

model = YOLO('${config.paths.yoloModel}')
results = model.predict('${imagePath}', conf=${config.yolo.inferenceConfidence}, verbose=False)

predictions = []
for r in results:
    for i, box in enumerate(r.boxes):
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        name = model.names[cls]

        predictions.append({
            'id': f'pred_{i}',
            'x': x1,
            'y': y1,
            'width': x2 - x1,
            'height': y2 - y1,
            'classLabel': name,
            'confidence': conf
        })

print(json.dumps(predictions))
`

    const python = spawn(config.paths.pythonBin, ['-c', pythonScript])

    let stdout = ''
    let stderr = ''

    python.stdout.on('data', (data) => {
      stdout += data.toString()
    })

    python.stderr.on('data', (data) => {
      stderr += data.toString()
    })

    python.on('close', (code) => {
      const inferenceTime = Date.now() - startTime

      if (code !== 0) {
        logger.error(`YOLO inference failed: ${stderr}`)
        reject(new Error(`YOLO inference failed: ${stderr}`))
        return
      }

      try {
        const predictions = JSON.parse(stdout.trim())
        logger.info(`🤖 YOLO predicted ${predictions.length} boxes in ${inferenceTime}ms`)

        resolve({
          imageId,
          predictions,
          inferenceTime
        })
      } catch (e) {
        logger.error(`Failed to parse YOLO output: ${stdout}`)
        reject(new Error(`Failed to parse YOLO output: ${e}`))
      }
    })
  })
}

// Canonical 24-faction color map.
// blood_angels, dark_angels, space_wolves, black_templars, deathwatch, grey_knights
// are collapsed into space_marines — see remapExportLabel in annotationService.ts.
const FACTION_COLORS: Record<string, string> = {
  // Imperium
  'space_marines':      '#3b82f6',
  'adeptus_mechanicus': '#ef4444',
  'astra_militarum':    '#84cc16',
  'adeptus_custodes':   '#f59e0b',
  'adepta_sororitas':   '#fb7185',
  'imperial_knights':   '#d97706',
  'imperial_agents':    '#6366f1',
  // Chaos
  // death_guard, thousand_sons, world_eaters, emperors_children collapsed → chaos_space_marines
  'chaos_space_marines': '#991b1b',
  'chaos_daemons':       '#9333ea',
  'chaos_knights':       '#78716c',
  // Xenos
  'orks':               '#22c55e',
  'craftworld_aeldari': '#a855f7',
  'drukhari':           '#9d174d',
  'harlequins':         '#f97316',
  'ynnari':             '#e879f9',
  'tau_empire':         '#0ea5e9',
  'tyranids':           '#a16207',
  'genestealer_cults':  '#4c1d95',
  'necrons':            '#22d3ee',
  'leagues_of_votann':  '#92400e',
}

// Maps model output class names → canonical faction keys.
// Run 2 classes: adeptus_mechanicus, chaos_knights, chaos_space_marines, custodes,
//   death_guard, deathwatch, eldar, genestealer_cult, grey_knights, imperial_guard,
//   necrons, orks, space_marines, thousand_sons, tyranids
// Chapter marines (blood_angels etc.) are remapped to space_marines here and at export.
const MODEL_CLASS_ALIASES: Record<string, string> = {
  'eldar':            'craftworld_aeldari',
  'imperial_guard':   'astra_militarum',
  'custodes':         'adeptus_custodes',
  'genestealer_cult': 'genestealer_cults',
  // Loyalist chapters → space_marines
  'blood_angels':     'space_marines',
  'dark_angels':      'space_marines',
  'space_wolves':     'space_marines',
  'black_templars':   'space_marines',
  'deathwatch':       'space_marines',
  'grey_knights':     'space_marines',
  // Traitor legions → chaos_space_marines
  'death_guard':      'chaos_space_marines',
  'thousand_sons':    'chaos_space_marines',
  'world_eaters':     'chaos_space_marines',
  'emperors_children':'chaos_space_marines',
}

export interface ConsumerDetection {
  faction: string
  confidence: number
  bbox: { x: number; y: number; width: number; height: number }
}

export interface FactionSummary {
  faction: string
  count: number
  avgConfidence: number
  color: string
}

export interface DetectionResult {
  imageWidth: number
  imageHeight: number
  detections: ConsumerDetection[]
  summary: FactionSummary[]
  totalDetected: number
  inferenceTimeMs: number
}

/**
 * Run YOLO inference and return consumer-friendly grouped results
 */
export async function detectAndSummarize(imagePath: string): Promise<DetectionResult> {
  const sharp = await import('sharp')
  const metadata = await sharp.default(imagePath).metadata()
  const imageWidth = metadata.width || 0
  const imageHeight = metadata.height || 0

  const result = await predictBoxes(imagePath, 'detect')

  const detections: ConsumerDetection[] = result.predictions.map(p => ({
    // Remap old model class names to canonical faction keys
    faction: MODEL_CLASS_ALIASES[p.classLabel] ?? p.classLabel,
    confidence: p.confidence,
    bbox: { x: p.x, y: p.y, width: p.width, height: p.height }
  }))

  // Group by faction
  const factionMap = new Map<string, ConsumerDetection[]>()
  for (const det of detections) {
    const existing = factionMap.get(det.faction) || []
    existing.push(det)
    factionMap.set(det.faction, existing)
  }

  const summary: FactionSummary[] = Array.from(factionMap.entries())
    .map(([faction, dets]) => ({
      faction,
      count: dets.length,
      avgConfidence: dets.reduce((sum, d) => sum + d.confidence, 0) / dets.length,
      color: FACTION_COLORS[faction] || '#60a5fa'
    }))
    .sort((a, b) => b.count - a.count)

  return {
    imageWidth,
    imageHeight,
    detections,
    summary,
    totalDetected: detections.length,
    inferenceTimeMs: result.inferenceTime
  }
}

/**
 * Check if the YOLO model is available
 */
export async function isModelAvailable(): Promise<boolean> {
  const fs = await import('fs/promises')
  try {
    await fs.access(config.paths.yoloModel)
    return true
  } catch {
    return false
  }
}
