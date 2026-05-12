import { describe, it, expect } from 'vitest'
import { apiToBbox, bboxToApi, type ApiAnnotation } from '../utils/annotationWire'
import type { BboxAnnotation } from '../types'

describe('annotationWire', () => {
  const WIRE: ApiAnnotation = {
    id: 'bbox-1',
    modelBbox: { x: 10, y: 20, width: 100, height: 200 },
    baseBbox: { x: 12, y: 180, width: 96, height: 40 },
    classLabel: 'space_marines',
    unit_slug: 'intercessors',
    confidence: 0.83,
    validationAction: 'accepted',
    originalPrediction: true,
  }
  const UI: BboxAnnotation = {
    id: 'bbox-1',
    x: 10,
    y: 20,
    width: 100,
    height: 200,
    baseBbox: { x: 12, y: 180, width: 96, height: 40 },
    classLabel: 'space_marines',
    unit_slug: 'intercessors',
    confidence: 0.83,
    validationAction: 'accepted',
    originalPrediction: true,
  }

  it('apiToBbox flattens modelBbox into top-level x/y/width/height', () => {
    expect(apiToBbox(WIRE)).toEqual(UI)
  })

  it('bboxToApi wraps top-level coords back into modelBbox', () => {
    expect(bboxToApi(UI)).toEqual(WIRE)
  })

  it('round-trip preserves the full payload', () => {
    expect(apiToBbox(bboxToApi(UI))).toEqual(UI)
    expect(bboxToApi(apiToBbox(WIRE))).toEqual(WIRE)
  })

  it('handles minimum payload (no optional fields)', () => {
    const minimalWire: ApiAnnotation = {
      id: 'b',
      modelBbox: { x: 0, y: 0, width: 1, height: 1 },
      classLabel: 'orks',
    }
    const result = apiToBbox(minimalWire)
    expect(result.id).toBe('b')
    expect(result.x).toBe(0)
    expect(result.baseBbox).toBeUndefined()
    expect(result.unit_slug).toBeUndefined()
    expect(bboxToApi(result)).toEqual(minimalWire)
  })
})
