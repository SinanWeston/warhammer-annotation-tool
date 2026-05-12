/**
 * Wire-schema marshalling for annotations.
 *
 * The backend's annotation JSON wraps the box coords inside `modelBbox`
 * (matches `ImageAnnotation.annotations[].modelBbox` in the Node service);
 * the canvas/UI works with the flatter `BboxAnnotation` shape (x/y/width/
 * height at the top level). Two pure helpers translate between them.
 *
 * Before this util the conversion was inlined at four call sites in
 * AnnotationInterface.tsx (loadNextImage, loadSpecificImage,
 * prefetchNextImage, saveAnnotations) — meaning a wire schema change
 * needed four edits in sync. One util + one type now.
 */

import type { BboxAnnotation } from '../types'

/** Wire shape returned by `/api/annotate/{next,image/:id}` (the per-bbox
 *  payload inside `annotation.annotations[]`) and POSTed back to
 *  `/api/annotate/save`. Mirrors `BboxAnnotationData` in
 *  backend/src/services/annotationService.ts. */
export interface ApiAnnotation {
  id: string
  modelBbox: { x: number; y: number; width: number; height: number }
  baseBbox?: { x: number; y: number; width: number; height: number }
  classLabel: string
  unit_slug?: string
  confidence?: number
  validationAction?: 'accepted' | 'rejected' | 'redrawn'
  originalPrediction?: boolean
}

/** Flatten a wire annotation into the UI shape used by BboxAnnotator. */
export function apiToBbox(ann: ApiAnnotation): BboxAnnotation {
  return {
    id: ann.id,
    x: ann.modelBbox.x,
    y: ann.modelBbox.y,
    width: ann.modelBbox.width,
    height: ann.modelBbox.height,
    classLabel: ann.classLabel,
    unit_slug: ann.unit_slug,
    baseBbox: ann.baseBbox,
    confidence: ann.confidence,
    validationAction: ann.validationAction,
    originalPrediction: ann.originalPrediction,
  }
}

/** Wrap a UI annotation back into the wire shape for POSTing to /save. */
export function bboxToApi(b: BboxAnnotation): ApiAnnotation {
  return {
    id: b.id,
    modelBbox: { x: b.x, y: b.y, width: b.width, height: b.height },
    baseBbox: b.baseBbox,
    classLabel: b.classLabel,
    unit_slug: b.unit_slug,
    confidence: b.confidence,
    validationAction: b.validationAction,
    originalPrediction: b.originalPrediction,
  }
}
