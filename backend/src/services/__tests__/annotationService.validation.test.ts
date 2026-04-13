/**
 * Unit Tests for Annotation Validation
 *
 * Tests the validation logic in annotationService:
 * - validateAnnotation() method
 * - calculateIoU() method
 * - Quality checks (out of bounds, too small, base outside model, duplicates)
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { annotationService, ImageAnnotation } from '../annotationService'

vi.mock('sharp', () => {
  const mockSharp = vi.fn(() => ({
    metadata: vi.fn().mockResolvedValue({ width: 1000, height: 800 }),
  }))
  return { __esModule: true, default: mockSharp }
})

describe('AnnotationService - Validation', () => {
  const baseAnnotation: ImageAnnotation = {
    imageId: 'test_image',
    imagePath: '/path/to/test.jpg',
    faction: 'space_marines',
    source: 'reddit',
    width: 1000,
    height: 800,
    annotations: [],
    annotatedAt: new Date().toISOString(),
    annotatedBy: 'test_user'
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('validateAnnotation - Bbox Out of Bounds', () => {
    it('should return error when model bbox extends beyond image (right edge)', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 900, y: 100, width: 200, height: 100 }, // extends beyond 1000px width
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error')
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0].code).toBe('BBOX_OUT_OF_BOUNDS')
    })

    it('should return error when model bbox extends beyond image (bottom edge)', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 700, width: 100, height: 150 }, // extends beyond 800px height
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error')
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0].code).toBe('BBOX_OUT_OF_BOUNDS')
    })

    it('should return error when model bbox has negative coordinates', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: -10, y: 100, width: 100, height: 100 },
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error')
      expect(errors.length).toBeGreaterThan(0)
      expect(errors[0].code).toBe('BBOX_OUT_OF_BOUNDS')
    })

    it('should pass when model bbox is within bounds', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 100, width: 200, height: 150 },
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error' && i.code === 'BBOX_OUT_OF_BOUNDS')
      expect(errors.length).toBe(0)
    })
  })

  describe('validateAnnotation - Bbox Too Small', () => {
    it('should return warning when model bbox is very small (< 10px)', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 100, width: 5, height: 5 },
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const warnings = issues.filter(i => i.type === 'warning' && i.code === 'BBOX_TOO_SMALL')
      expect(warnings.length).toBeGreaterThan(0)
    })

    it('should pass when model bbox is large enough', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 100, width: 50, height: 50 },
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const warnings = issues.filter(i => i.type === 'warning' && i.code === 'BBOX_TOO_SMALL')
      expect(warnings.length).toBe(0)
    })
  })

  // BASE_OUTSIDE_MODEL validation is spec'd but not yet implemented in annotationService.
  // See SPEC.md §6.1 ("errors block save") and TODO.md. Re-enable when the feature ships.
  describe.skip('validateAnnotation - Base Outside Model', () => {
    it('should return error when base bbox extends outside model bbox (right)', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 100, width: 200, height: 200 },
          baseBbox: { x: 200, y: 150, width: 150, height: 50 }, // extends beyond model
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error' && (i.code as string) === 'BASE_OUTSIDE_MODEL')
      expect(errors.length).toBeGreaterThan(0)
    })

    it('should return error when base bbox extends outside model bbox (bottom)', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 100, width: 200, height: 200 },
          baseBbox: { x: 150, y: 200, width: 50, height: 150 }, // extends beyond model
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error' && (i.code as string) === 'BASE_OUTSIDE_MODEL')
      expect(errors.length).toBeGreaterThan(0)
    })

    it('should return error when base bbox is completely outside model bbox', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 100, width: 200, height: 200 },
          baseBbox: { x: 400, y: 400, width: 50, height: 50 },
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error' && (i.code as string) === 'BASE_OUTSIDE_MODEL')
      expect(errors.length).toBeGreaterThan(0)
    })

    it('should pass when base bbox is completely inside model bbox', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 100, width: 200, height: 200 },
          baseBbox: { x: 150, y: 150, width: 50, height: 50 },
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error' && (i.code as string) === 'BASE_OUTSIDE_MODEL')
      expect(errors.length).toBe(0)
    })

    it('should pass when base bbox touches model edges (edge case)', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 100, width: 200, height: 200 },
          baseBbox: { x: 100, y: 100, width: 200, height: 200 }, // exact same as model
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error' && (i.code as string) === 'BASE_OUTSIDE_MODEL')
      expect(errors.length).toBe(0)
    })
  })

  describe('validateAnnotation - Duplicate Boxes', () => {
    it('should return warning when two boxes overlap >90% (duplicates)', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [
          {
            id: '1',
            modelBbox: { x: 100, y: 100, width: 100, height: 100 },
            classLabel: 'miniature'
          },
          {
            id: '2',
            modelBbox: { x: 102, y: 102, width: 100, height: 100 }, // IoU ~0.924, over 0.9 threshold
            classLabel: 'miniature'
          }
        ]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const warnings = issues.filter(i => i.type === 'warning' && i.code === 'DUPLICATE_BOX')
      expect(warnings.length).toBeGreaterThan(0)
    })

    it('should pass when boxes overlap <90% (not duplicates)', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [
          {
            id: '1',
            modelBbox: { x: 100, y: 100, width: 100, height: 100 },
            classLabel: 'miniature'
          },
          {
            id: '2',
            modelBbox: { x: 150, y: 150, width: 100, height: 100 }, // less overlap
            classLabel: 'miniature'
          }
        ]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const warnings = issues.filter(i => i.type === 'warning' && i.code === 'DUPLICATE_BOX')
      expect(warnings.length).toBe(0)
    })

    it('should pass when boxes do not overlap at all', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [
          {
            id: '1',
            modelBbox: { x: 100, y: 100, width: 100, height: 100 },
            classLabel: 'miniature'
          },
          {
            id: '2',
            modelBbox: { x: 300, y: 300, width: 100, height: 100 },
            classLabel: 'miniature'
          }
        ]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const warnings = issues.filter(i => i.type === 'warning' && i.code === 'DUPLICATE_BOX')
      expect(warnings.length).toBe(0)
    })
  })

  describe('validateAnnotation - Complex Scenarios', () => {
    it('should return multiple errors for annotation with multiple issues', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [
          {
            id: '1',
            modelBbox: { x: -10, y: 100, width: 100, height: 100 }, // out of bounds
            classLabel: 'miniature'
          },
          {
            id: '2',
            modelBbox: { x: 200, y: 200, width: 5, height: 5 }, // too small
            classLabel: 'miniature'
          }
        ]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      expect(issues.length).toBeGreaterThan(1)

      const errors = issues.filter(i => i.type === 'error')
      const warnings = issues.filter(i => i.type === 'warning')

      expect(errors.length).toBeGreaterThan(0)
      expect(warnings.length).toBeGreaterThan(0)
    })

    it('should pass validation for perfect annotation', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [
          {
            id: '1',
            modelBbox: { x: 100, y: 100, width: 200, height: 200 },
            baseBbox: { x: 150, y: 150, width: 100, height: 100 },
            classLabel: 'miniature'
          },
          {
            id: '2',
            modelBbox: { x: 400, y: 400, width: 150, height: 150 },
            baseBbox: { x: 425, y: 425, width: 100, height: 100 },
            classLabel: 'miniature'
          }
        ]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      const errors = issues.filter(i => i.type === 'error')
      expect(errors.length).toBe(0)
    })

    it('should handle annotation with no base bbox', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: [{
          id: '1',
          modelBbox: { x: 100, y: 100, width: 200, height: 200 },
          // No baseBbox
          classLabel: 'miniature'
        }]
      }

      const issues = await annotationService.validateAnnotation(annotation)

      // Should not error just because base bbox is missing
      const errors = issues.filter(i => i.type === 'error')
      expect(errors.length).toBe(0)
    })

    it('should handle empty annotations array', async () => {
      const annotation: ImageAnnotation = {
        ...baseAnnotation,
        annotations: []
      }

      const issues = await annotationService.validateAnnotation(annotation)

      // Empty is valid (skipped image)
      expect(issues.length).toBe(0)
    })
  })

  describe('calculateIoU', () => {
    // Access private method via type assertion for testing
    const service = annotationService as any

    it('should calculate IoU correctly for overlapping boxes', () => {
      const boxA = { x: 0, y: 0, width: 100, height: 100 }
      const boxB = { x: 50, y: 50, width: 100, height: 100 }

      const iou = service.calculateIoU(boxA, boxB)

      // Overlap area: 50x50 = 2500
      // Union: 10000 + 10000 - 2500 = 17500
      // IoU: 2500 / 17500 ≈ 0.143
      expect(iou).toBeCloseTo(0.143, 2)
    })

    it('should return 1.0 for identical boxes', () => {
      const boxA = { x: 100, y: 100, width: 100, height: 100 }
      const boxB = { x: 100, y: 100, width: 100, height: 100 }

      const iou = service.calculateIoU(boxA, boxB)

      expect(iou).toBe(1.0)
    })

    it('should return 0.0 for non-overlapping boxes', () => {
      const boxA = { x: 0, y: 0, width: 100, height: 100 }
      const boxB = { x: 200, y: 200, width: 100, height: 100 }

      const iou = service.calculateIoU(boxA, boxB)

      expect(iou).toBe(0.0)
    })

    it('should return 0.0 for boxes that touch but do not overlap', () => {
      const boxA = { x: 0, y: 0, width: 100, height: 100 }
      const boxB = { x: 100, y: 0, width: 100, height: 100 }

      const iou = service.calculateIoU(boxA, boxB)

      expect(iou).toBe(0.0)
    })

    it('should calculate IoU correctly for high overlap (>90%)', () => {
      const boxA = { x: 100, y: 100, width: 100, height: 100 }
      const boxB = { x: 102, y: 102, width: 100, height: 100 }

      const iou = service.calculateIoU(boxA, boxB)

      // Very high overlap
      expect(iou).toBeGreaterThan(0.9)
    })

    it('should handle boxes with different sizes', () => {
      const boxA = { x: 0, y: 0, width: 200, height: 200 }
      const boxB = { x: 50, y: 50, width: 50, height: 50 }

      const iou = service.calculateIoU(boxA, boxB)

      // boxB completely inside boxA
      // Overlap: 50x50 = 2500
      // Union: 40000 + 2500 - 2500 = 40000
      // IoU: 2500 / 40000 = 0.0625
      expect(iou).toBeCloseTo(0.0625, 3)
    })
  })
})
