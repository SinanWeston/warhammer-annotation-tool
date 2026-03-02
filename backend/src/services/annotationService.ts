/**
 * Annotation Service
 *
 * Manages the annotation workflow for training data:
 * - Lists images that need annotation
 * - Saves bbox annotations (model + base)
 * - Tracks progress
 * - Exports to YOLO format
 */

import fs from 'fs/promises'
import path from 'path'
import { randomUUID } from 'crypto'
import sharp from 'sharp'
import logger from '../utils/logger'

export interface QualityIssue {
  type: 'error' | 'warning'
  code: 'BBOX_OUT_OF_BOUNDS' | 'BBOX_TOO_SMALL' | 'DUPLICATE_BOX'
  message: string
  bboxId?: string
}

export interface ImageAnnotation {
  imageId: string
  imagePath: string
  faction: string
  source: 'reddit' | 'dakkadakka'
  width: number
  height: number
  annotations: BboxAnnotationData[]
  // AI prediction validation data (for training improvements)
  rejectedPredictions?: RejectedPrediction[]  // False positives for hard negative mining
  redrawnPredictions?: RejectedPrediction[]   // Wrong boxes that were corrected
  annotatedAt: string
  annotatedBy: string
}

export interface BboxAnnotationData {
  id: string
  modelBbox: {
    x: number  // Pixels
    y: number
    width: number
    height: number
  }
  baseBbox?: {
    x: number
    y: number
    width: number
    height: number
  }
  classLabel: string  // Unit name (e.g., "hormagaunt")
  confidence?: number
  // AI prediction tracking
  validationAction?: 'accepted' | 'rejected' | 'redrawn'
  originalPrediction?: boolean  // Was this from AI?
}

export interface RejectedPrediction {
  id: string
  modelBbox: {
    x: number
    y: number
    width: number
    height: number
  }
  classLabel: string
  confidence?: number
}

export interface AnnotationProgress {
  totalImages: number
  annotatedImages: number
  percentComplete: number
  byFaction: Record<string, { total: number; annotated: number }>
}

export class AnnotationService {
  private trainingDataPath: string
  private annotationsPath: string
  public onAnnotationSaved: (() => void) | null = null

  constructor() {
    this.trainingDataPath = path.join(__dirname, '../../training_data')
    this.annotationsPath = path.join(__dirname, '../../training_data_annotations')
  }

  /**
   * Initialize annotation system
   * Creates annotations directory if it doesn't exist
   */
  async initialize(): Promise<void> {
    try {
      await fs.mkdir(this.annotationsPath, { recursive: true })
      logger.info('📝 Annotation service initialized')
    } catch (error) {
      logger.error('Failed to initialize annotation service:', error)
      throw error
    }
  }

  // Per-faction image caps — target 400 annotations per faction
  private factionLimits: Record<string, number> = {
    default: 400,
  }

  private getFactionLimit(faction: string): number {
    return this.factionLimits[faction] ?? this.factionLimits.default
  }

  // Kept for progress calculation
  private get perFactionLimit(): number {
    return this.factionLimits.default
  }

  /**
   * Get list of all images available for annotation
   * Returns image metadata including path, faction, source
   * Limited to perFactionLimit (110) images per faction for focused annotation
   */
  async getImageList(includeAnnotated: boolean = false): Promise<Array<{
    imageId: string
    imagePath: string
    faction: string
    source: 'reddit' | 'dakkadakka'
    isAnnotated: boolean
  }>> {
    const images: Array<{
      imageId: string
      imagePath: string
      faction: string
      source: 'reddit' | 'dakkadakka'
      isAnnotated: boolean
    }> = []

    // Track count per faction
    const factionCounts: Record<string, number> = {}

    try {
      const factions = await fs.readdir(this.trainingDataPath)

      for (const faction of factions) {
        const factionPath = path.join(this.trainingDataPath, faction)
        const stat = await fs.stat(factionPath)

        if (!stat.isDirectory()) continue
        if (faction === 'hormagaunts' || faction === 'tyranid_ripper_swarm') continue
        if (faction === 'reddit' || faction === 'dakkadakka') continue  // Skip non-faction dirs

        factionCounts[faction] = 0

        // Check reddit and dakkadakka subdirectories
        for (const source of ['reddit', 'dakkadakka'] as const) {
          const sourcePath = path.join(factionPath, source)

          try {
            const files = await fs.readdir(sourcePath)

            for (const file of files) {
              // Stop if we've hit the limit for this faction
              if (factionCounts[faction] >= this.getFactionLimit(faction)) break

              if (!file.match(/\.(jpg|jpeg|png|gif|webp)$/i)) continue

              const imagePath = path.join(sourcePath, file)
              const imageId = this.getImageId(imagePath)

              // Skip flagged images entirely
              const isFlagged = await this.isImageFlagged(imageId)
              if (isFlagged) continue

              const isAnnotated = await this.isImageAnnotated(imageId)

              // Count ALL images toward limit (not just filtered ones)
              factionCounts[faction]++

              // But only add to results if it matches the filter
              if (includeAnnotated || !isAnnotated) {
                images.push({
                  imageId,
                  imagePath,
                  faction,
                  source,
                  isAnnotated
                })
              }
            }
          } catch (error) {
            // Source directory doesn't exist, skip
            continue
          }
        }
      }

      logger.info(`📋 Found ${images.length} images (${this.perFactionLimit}/faction, includeAnnotated: ${includeAnnotated})`)
      return images
    } catch (error) {
      logger.error('Error getting image list:', error)
      throw error
    }
  }

  /**
   * Get next unannotated image
   * When prioritize=true, delegates to active learning service for confidence-based ordering
   * Returns null if all images are annotated
   */
  async getNextImage(prioritize: boolean = false, faction?: string): Promise<{
    imageId: string
    imagePath: string
    faction: string
    source: 'reddit' | 'dakkadakka'
    confidenceScore?: number
  } | null> {
    let images = await this.getImageList(false)
    if (faction) {
      images = images.filter(img => img.faction === faction)
    }
    if (images.length === 0) return null

    if (prioritize) {
      try {
        const { activeLearningService } = await import('./activeLearningService')
        const prioritized = activeLearningService.getNextPrioritizedImage(images)
        if (prioritized) return prioritized
      } catch {
        // Fall through to default behavior
      }
    }

    return images[0]
  }

  /**
   * Validate annotation quality
   * Returns list of errors and warnings
   */
  async validateAnnotation(annotation: ImageAnnotation): Promise<QualityIssue[]> {
    const issues: QualityIssue[] = []

    try {
      // Get image dimensions
      const metadata = await sharp(annotation.imagePath).metadata()
      const imgWidth = metadata.width!
      const imgHeight = metadata.height!

      for (const bbox of annotation.annotations) {
        const model = bbox.modelBbox

        // 1. Check model bbox is within image bounds
        if (
          model.x < 0 ||
          model.y < 0 ||
          model.x + model.width > imgWidth ||
          model.y + model.height > imgHeight
        ) {
          issues.push({
            type: 'error',
            code: 'BBOX_OUT_OF_BOUNDS',
            message: `Model bbox extends beyond image (${model.x},${model.y} ${model.width}x${model.height})`,
            bboxId: bbox.id,
          })
        }

        // 2. Check minimum size (avoid tiny accidental boxes)
        if (model.width < 10 || model.height < 10) {
          issues.push({
            type: 'warning',
            code: 'BBOX_TOO_SMALL',
            message: `Bbox very small (${model.width}x${model.height}px)`,
            bboxId: bbox.id,
          })
        }
      }

      // 3. Check for duplicate/overlapping boxes
      for (let i = 0; i < annotation.annotations.length; i++) {
        for (let j = i + 1; j < annotation.annotations.length; j++) {
          const iou = this.calculateIoU(
            annotation.annotations[i].modelBbox,
            annotation.annotations[j].modelBbox
          )

          if (iou > 0.9) {
            // 90%+ overlap = likely duplicate
            issues.push({
              type: 'warning',
              code: 'DUPLICATE_BOX',
              message: `High overlap (${(iou * 100).toFixed(0)}%) between boxes`,
              bboxId: annotation.annotations[i].id,
            })
          }
        }
      }
    } catch (error) {
      logger.error('Error validating annotation:', error)
      // Don't throw - return validation error as issue
      issues.push({
        type: 'error',
        code: 'BBOX_OUT_OF_BOUNDS',
        message: `Failed to validate: ${error instanceof Error ? error.message : 'Unknown error'}`,
      })
    }

    return issues
  }

  /**
   * Validate all saved annotations
   * Returns summary of issues across entire dataset
   */
  async validateAllAnnotations(): Promise<{
    totalAnnotations: number
    validAnnotations: number
    invalidAnnotations: number
    warningAnnotations: number
    totalErrors: number
    totalWarnings: number
    issues: Array<{
      imageId: string
      imagePath: string
      errors: QualityIssue[]
      warnings: QualityIssue[]
    }>
  }> {
    logger.info('🔍 Validating all annotations...')

    const images = await this.getImageList(true)
    const annotatedImages = images.filter(img => img.isAnnotated)

    let validCount = 0
    let invalidCount = 0
    let warningCount = 0
    let totalErrors = 0
    let totalWarnings = 0
    const issues: Array<{
      imageId: string
      imagePath: string
      errors: QualityIssue[]
      warnings: QualityIssue[]
    }> = []

    for (const img of annotatedImages) {
      const annotation = await this.getAnnotation(img.imageId)
      if (!annotation) continue

      const validationIssues = await this.validateAnnotation(annotation)
      const errors = validationIssues.filter(i => i.type === 'error')
      const warnings = validationIssues.filter(i => i.type === 'warning')

      if (errors.length > 0) {
        invalidCount++
        totalErrors += errors.length
      } else if (warnings.length > 0) {
        warningCount++
        validCount++
      } else {
        validCount++
      }

      totalWarnings += warnings.length

      if (errors.length > 0 || warnings.length > 0) {
        issues.push({
          imageId: img.imageId,
          imagePath: img.imagePath,
          errors,
          warnings,
        })
      }
    }

    logger.info(`✅ Validation complete: ${validCount}/${annotatedImages.length} valid, ${invalidCount} invalid, ${warningCount} with warnings`)

    return {
      totalAnnotations: annotatedImages.length,
      validAnnotations: validCount,
      invalidAnnotations: invalidCount,
      warningAnnotations: warningCount,
      totalErrors,
      totalWarnings,
      issues,
    }
  }

  /**
   * Calculate Intersection over Union for two bboxes
   */
  private calculateIoU(
    a: { x: number; y: number; width: number; height: number },
    b: { x: number; y: number; width: number; height: number }
  ): number {
    // Convert to x1, y1, x2, y2
    const a_x1 = a.x
    const a_y1 = a.y
    const a_x2 = a.x + a.width
    const a_y2 = a.y + a.height

    const b_x1 = b.x
    const b_y1 = b.y
    const b_x2 = b.x + b.width
    const b_y2 = b.y + b.height

    // Calculate intersection
    const x1 = Math.max(a_x1, b_x1)
    const y1 = Math.max(a_y1, b_y1)
    const x2 = Math.min(a_x2, b_x2)
    const y2 = Math.min(a_y2, b_y2)

    if (x2 < x1 || y2 < y1) return 0 // No overlap

    const intersection = (x2 - x1) * (y2 - y1)
    const areaA = a.width * a.height
    const areaB = b.width * b.height
    const union = areaA + areaB - intersection

    return intersection / union
  }

  /**
   * Save annotation for an image
   */
  async saveAnnotation(annotation: ImageAnnotation): Promise<void> {
    try {
      const annotationPath = this.getAnnotationPath(annotation.imageId)
      const annotationDir = path.dirname(annotationPath)

      // Create directory if it doesn't exist
      await fs.mkdir(annotationDir, { recursive: true })

      // Save annotation as JSON
      await fs.writeFile(
        annotationPath,
        JSON.stringify(annotation, null, 2),
        'utf-8'
      )

      const rejectedCount = annotation.rejectedPredictions?.length || 0
      const redrawnCount = annotation.redrawnPredictions?.length || 0
      const aiAccepted = annotation.annotations.filter(a => a.originalPrediction).length
      logger.info(`✅ Saved annotation for ${annotation.imageId} (${annotation.annotations.length} boxes, ${aiAccepted} AI-accepted, ${rejectedCount} rejected, ${redrawnCount} redrawn)`)

      // Invalidate dashboard cache
      if (this.onAnnotationSaved) {
        this.onAnnotationSaved()
      }
    } catch (error) {
      logger.error('Error saving annotation:', error)
      throw error
    }
  }

  /**
   * Get annotation for an image
   * Returns null if image is not annotated
   */
  async getAnnotation(imageId: string): Promise<ImageAnnotation | null> {
    try {
      const annotationPath = this.getAnnotationPath(imageId)
      const data = await fs.readFile(annotationPath, 'utf-8')
      return JSON.parse(data)
    } catch (error) {
      // Annotation doesn't exist
      return null
    }
  }

  /**
   * Check if image is annotated
   */
  async isImageAnnotated(imageId: string): Promise<boolean> {
    const annotationPath = this.getAnnotationPath(imageId)
    try {
      await fs.access(annotationPath)
      return true
    } catch {
      return false
    }
  }

  /**
   * Check if an image is flagged as unusable
   */
  async isImageFlagged(imageId: string): Promise<boolean> {
    const flagPath = path.join(this.annotationsPath, `${imageId}.skip.json`)
    try {
      await fs.access(flagPath)
      return true
    } catch {
      return false
    }
  }

  /**
   * Flag an image as unusable (permanently skip it)
   */
  async flagImage(imageId: string, reason?: string): Promise<void> {
    const flagPath = path.join(this.annotationsPath, `${imageId}.skip.json`)
    const flagData = {
      imageId,
      flaggedAt: new Date().toISOString(),
      reason: reason || 'unusable'
    }
    await fs.writeFile(flagPath, JSON.stringify(flagData, null, 2))
    logger.info(`🚫 Flagged image ${imageId} as unusable`)
  }

  /**
   * Get count of flagged images (total and per faction)
   */
  async getFlaggedCount(): Promise<{ total: number; byFaction: Record<string, number> }> {
    const byFaction: Record<string, number> = {}
    let total = 0
    try {
      const files = await fs.readdir(this.annotationsPath)
      for (const file of files) {
        if (!file.endsWith('.skip.json')) continue
        total++
        // Extract faction from the imageId (format: faction_source_filename)
        const imageId = file.replace('.skip.json', '')
        const parts = imageId.split('_')
        // Faction can be multi-word (e.g. chaos_space_marines_reddit_img1)
        // We need to find the source separator (reddit or dakkadakka)
        const redditIdx = parts.indexOf('reddit')
        const dakkaIdx = parts.indexOf('dakkadakka')
        const sepIdx = redditIdx >= 0 ? redditIdx : dakkaIdx
        if (sepIdx > 0) {
          const faction = parts.slice(0, sepIdx).join('_')
          byFaction[faction] = (byFaction[faction] || 0) + 1
        }
      }
    } catch {
      // annotations dir doesn't exist yet
    }
    return { total, byFaction }
  }

  /**
   * Get annotation progress statistics
   * Shows progress toward the per-faction limit (110 per faction)
   */
  async getProgress(): Promise<AnnotationProgress> {
    const allImages = await this.getImageList(true)
    const annotatedImages = allImages.filter(img => img.isAnnotated)

    const byFaction: Record<string, { total: number; annotated: number }> = {}

    for (const img of allImages) {
      if (!byFaction[img.faction]) {
        byFaction[img.faction] = { total: 0, annotated: 0 }
      }
      byFaction[img.faction].total++
      if (img.isAnnotated) {
        byFaction[img.faction].annotated++
      }
    }

    // Calculate total target using per-faction caps
    const totalTarget = Object.keys(byFaction).reduce(
      (sum, faction) => sum + this.getFactionLimit(faction), 0
    )

    return {
      totalImages: totalTarget,  // Show target, not raw count
      annotatedImages: annotatedImages.length,
      percentComplete: (annotatedImages.length / totalTarget) * 100,
      byFaction
    }
  }

  /**
   * Generate unique image ID from path
   */
  private getImageId(imagePath: string): string {
    // Use relative path from training_data as ID
    const relativePath = path.relative(this.trainingDataPath, imagePath)
    return relativePath.replace(/[\/\\]/g, '_').replace(/\.[^.]+$/, '')
  }

  /**
   * Get annotation file path for an image ID
   */
  private getAnnotationPath(imageId: string): string {
    return path.join(this.annotationsPath, `${imageId}.json`)
  }

  /**
   * Get random annotated sample images for a faction (for consistency audit)
   */
  async getSampleImages(faction: string, count: number = 9): Promise<Array<{
    imageId: string
    imageBase64: string
    width: number
    height: number
    annotations: BboxAnnotationData[]
  }>> {
    const images = await this.getImageList(true)
    const annotated = images.filter(img => img.faction === faction && img.isAnnotated)

    // Shuffle and take N
    const shuffled = [...annotated].sort(() => Math.random() - 0.5).slice(0, count)
    const results = []

    for (const img of shuffled) {
      try {
        const annotation = await this.getAnnotation(img.imageId)
        if (!annotation || annotation.annotations.length === 0) continue

        const imageBuffer = await fs.readFile(img.imagePath)
        const sharpModule = await import('sharp')
        const metadata = await sharpModule.default(img.imagePath).metadata()

        results.push({
          imageId: img.imageId,
          imageBase64: `data:image/jpeg;base64,${imageBuffer.toString('base64')}`,
          width: metadata.width || 0,
          height: metadata.height || 0,
          annotations: annotation.annotations
        })
      } catch {
        continue
      }
    }

    return results
  }

  /**
   * Export annotations to YOLO format
   * Creates train/val split and converts to YOLO-pose format
   */
  async exportToYOLO(outputPath: string, trainSplit: number = 0.8, options?: { balanced?: boolean; balancedCap?: number }): Promise<{
    trainImages: number
    valImages: number
    classesFile: string
  }> {
    logger.info('🔄 Exporting annotations to YOLO format...')

    // Get all annotated images
    const images = await this.getImageList(true)
    const annotatedImages = images.filter(img => img.isAnnotated)

    if (annotatedImages.length === 0) {
      throw new Error('No annotated images found')
    }

    // Create output directories
    const imagesTrainDir = path.join(outputPath, 'images', 'train')
    const imagesValDir = path.join(outputPath, 'images', 'val')
    const labelsTrainDir = path.join(outputPath, 'labels', 'train')
    const labelsValDir = path.join(outputPath, 'labels', 'val')

    await fs.mkdir(imagesTrainDir, { recursive: true })
    await fs.mkdir(imagesValDir, { recursive: true })
    await fs.mkdir(labelsTrainDir, { recursive: true })
    await fs.mkdir(labelsValDir, { recursive: true })

    // Collect all unique classes
    const classesSet = new Set<string>()
    let annotations: Array<{ image: typeof annotatedImages[0]; annotation: ImageAnnotation }> = []

    for (const img of annotatedImages) {
      const annotation = await this.getAnnotation(img.imageId)
      // Only include images with actual annotations (skip empty/skipped ones)
      if (annotation && annotation.annotations.length > 0) {
        annotations.push({ image: img, annotation })
        annotation.annotations.forEach(ann => classesSet.add(ann.classLabel))
      }
    }

    // Balanced export: cap each faction at the minimum faction count (or custom cap)
    if (options?.balanced) {
      const byFaction = new Map<string, typeof annotations>()
      for (const entry of annotations) {
        const faction = entry.image.faction
        const existing = byFaction.get(faction) || []
        existing.push(entry)
        byFaction.set(faction, existing)
      }

      const minCount = options.balancedCap || Math.min(...Array.from(byFaction.values()).map(v => v.length))
      logger.info(`⚖️  Balanced export: capping each faction at ${minCount} images`)

      const balanced: typeof annotations = []
      for (const [faction, entries] of byFaction) {
        const shuffled = [...entries].sort(() => Math.random() - 0.5)
        const capped = shuffled.slice(0, minCount)
        balanced.push(...capped)
        logger.info(`   ${faction}: ${capped.length}/${entries.length}`)
      }
      annotations = balanced
    }

    logger.info(`📊 Exporting ${annotations.length} images with annotations (excluded ${annotatedImages.length - annotations.length} skipped/empty)`)

    // Create class mapping
    const classes = Array.from(classesSet).sort()
    const classToIndex = new Map(classes.map((cls, idx) => [cls, idx]))

    // Split train/val
    const shuffled = [...annotations].sort(() => Math.random() - 0.5)
    const trainCount = Math.floor(shuffled.length * trainSplit)
    const trainSet = shuffled.slice(0, trainCount)
    const valSet = shuffled.slice(trainCount)

    // Process train set
    for (const { image, annotation } of trainSet) {
      await this.exportImageAndLabel(
        image.imagePath,
        annotation,
        imagesTrainDir,
        labelsTrainDir,
        classToIndex,
        annotation.width,
        annotation.height
      )
    }

    // Process val set
    for (const { image, annotation } of valSet) {
      await this.exportImageAndLabel(
        image.imagePath,
        annotation,
        imagesValDir,
        labelsValDir,
        classToIndex,
        annotation.width,
        annotation.height
      )
    }

    // Write classes file
    const classesFile = path.join(outputPath, 'classes.txt')
    await fs.writeFile(classesFile, classes.join('\n'), 'utf-8')

    // Write YOLO data.yaml
    const yamlContent = `# YOLO Dataset Configuration
path: ${outputPath}
train: images/train
val: images/val

# Classes
nc: ${classes.length}
names: [${classes.map(c => `"${c}"`).join(', ')}]
`
    await fs.writeFile(path.join(outputPath, 'data.yaml'), yamlContent, 'utf-8')

    logger.info(`✅ YOLO export complete:`)
    logger.info(`   Train: ${trainSet.length} images`)
    logger.info(`   Val: ${valSet.length} images`)
    logger.info(`   Classes: ${classes.length}`)

    return {
      trainImages: trainSet.length,
      valImages: valSet.length,
      classesFile
    }
  }

  /**
   * Export single image and label to YOLO format
   */
  private async exportImageAndLabel(
    imagePath: string,
    annotation: ImageAnnotation,
    imagesDir: string,
    labelsDir: string,
    classToIndex: Map<string, number>,
    imageWidth: number,
    imageHeight: number
  ): Promise<void> {
    const imageName = path.basename(imagePath)
    const labelName = imageName.replace(/\.[^.]+$/, '.txt')

    // Copy image
    const destImagePath = path.join(imagesDir, imageName)
    await fs.copyFile(imagePath, destImagePath)

    // Convert annotations to YOLO format
    const yoloLines: string[] = []

    for (const ann of annotation.annotations) {
      const classIndex = classToIndex.get(ann.classLabel)
      if (classIndex === undefined) continue

      // Normalize bbox to [0, 1]
      // YOLO format: class x_center y_center width height
      const x_center = (ann.modelBbox.x + ann.modelBbox.width / 2) / imageWidth
      const y_center = (ann.modelBbox.y + ann.modelBbox.height / 2) / imageHeight
      const width = ann.modelBbox.width / imageWidth
      const height = ann.modelBbox.height / imageHeight

      const line = [
        classIndex,
        x_center.toFixed(6),
        y_center.toFixed(6),
        width.toFixed(6),
        height.toFixed(6)
      ].join(' ')

      yoloLines.push(line)
    }

    // Write label file
    const destLabelPath = path.join(labelsDir, labelName)
    await fs.writeFile(destLabelPath, yoloLines.join('\n'), 'utf-8')
  }
}

// Singleton instance
export const annotationService = new AnnotationService()
