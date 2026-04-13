/**
 * Centralized configuration.
 *
 * All environment-driven paths and thresholds live here. Services should
 * import from this module rather than reading process.env directly so the
 * defaults stay in one place.
 *
 * Loaded after dotenv.config() in index.ts, so env vars are populated.
 */

import path from 'path'

const REPO_ROOT = path.join(__dirname, '../../..')
const BACKEND_ROOT = path.join(__dirname, '../..')

function resolveOrDefault(envVar: string | undefined, defaultPath: string): string {
  return envVar ? path.resolve(envVar) : defaultPath
}

export const config = {
  port: parseInt(process.env.PORT || '3001', 10),
  isProduction: process.env.NODE_ENV === 'production',
  annotatorPassword: process.env.ANNOTATOR_PASSWORD,

  paths: {
    trainingData: resolveOrDefault(
      process.env.TRAINING_DATA_PATH,
      path.join(BACKEND_ROOT, 'training_data')
    ),
    annotations: resolveOrDefault(
      process.env.ANNOTATIONS_PATH,
      path.join(BACKEND_ROOT, 'training_data_annotations')
    ),
    proposals: resolveOrDefault(
      process.env.PROPOSALS_PATH,
      path.join(BACKEND_ROOT, 'training_data_proposals')
    ),
    confidenceScores: path.join(BACKEND_ROOT, 'confidence_scores.json'),
    yoloModel: resolveOrDefault(
      process.env.YOLO_MODEL_PATH,
      path.join(REPO_ROOT, 'runs/yolo11x_run2_best.pt')
    ),
    pythonBin: resolveOrDefault(
      process.env.YOLO_PYTHON_PATH,
      path.join(REPO_ROOT, 'yolo_env/bin/python3')
    ),
    batchInferenceScript: path.join(__dirname, '../services/batchYoloInference.py'),
  },

  annotation: {
    sources: (process.env.ANNOTATION_SOURCES || 'reddit,dakkadakka')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    perFactionLimit: parseInt(process.env.ANNOTATION_PER_FACTION_LIMIT || '400', 10),
  },

  yolo: {
    inferenceConfidence: parseFloat(process.env.YOLO_INFERENCE_CONFIDENCE || '0.25'),
    batchConfidence: parseFloat(process.env.YOLO_BATCH_CONFIDENCE || '0.10'),
  },
}
