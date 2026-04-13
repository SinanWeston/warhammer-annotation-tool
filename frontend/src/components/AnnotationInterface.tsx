/**
 * AnnotationInterface Component
 *
 * Full-featured annotation interface for labeling training data:
 * - Loads images from training_data
 * - Uses BboxAnnotator for drawing model + base bboxes
 * - Saves annotations to backend
 * - Tracks progress
 * - Navigation (next/previous/skip)
 */

import { useState, useEffect, useRef } from 'react'
import BboxAnnotator from './BboxAnnotator'
import QualityIssuesModal from './QualityIssuesModal'
import { BboxAnnotation } from '../types'
import { API_BASE } from '../lib/api'

// Mirrors EXPORT_LABEL_REMAP in annotationService.ts — keep in sync.
const FACTION_REMAP: Record<string, string> = {
  blood_angels: 'space_marines', dark_angels: 'space_marines',
  space_wolves: 'space_marines', black_templars: 'space_marines',
  deathwatch: 'space_marines', grey_knights: 'space_marines',
  death_guard: 'chaos_space_marines', thousand_sons: 'chaos_space_marines',
  world_eaters: 'chaos_space_marines', emperors_children: 'chaos_space_marines',
}
const remapFaction = (f: string) => FACTION_REMAP[f] ?? f

interface ImageData {
  imageId: string
  imagePath: string
  faction: string
  source: 'reddit' | 'dakkadakka'
  imageBase64?: string
  width?: number
  height?: number
}

interface AnnotationProgress {
  totalImages: number
  annotatedImages: number
  percentComplete: number
  byFaction: Record<string, { total: number; annotated: number }>
}

interface QualityIssue {
  type: 'error' | 'warning'
  code: string
  message: string
  bboxId?: string
}

interface AnnotationInterfaceProps {
  editImageId?: string | null
  onEditComplete?: () => void
  annotatorName?: string | null
}

export default function AnnotationInterface({ editImageId, onEditComplete, annotatorName }: AnnotationInterfaceProps = {}) {
  const [currentImage, setCurrentImage] = useState<ImageData | null>(null)
  const [annotations, setAnnotations] = useState<BboxAnnotation[]>([])
  const [progress, setProgress] = useState<AnnotationProgress | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [fetchingProgress, setFetchingProgress] = useState(false)

  // Quality issues state
  const [qualityErrors, setQualityErrors] = useState<QualityIssue[]>([])
  const [qualityWarnings, setQualityWarnings] = useState<QualityIssue[]>([])
  const [showQualityModal, setShowQualityModal] = useState(false)

  // AI prediction state
  const [predicting, setPredicting] = useState(false)
  const [predictions, setPredictions] = useState<BboxAnnotation[]>([])
  const [validationMode, setValidationMode] = useState(false)
  const [highlightedPrediction, setHighlightedPrediction] = useState<string | null>(null)

  // Edit mode state
  const [editMode, setEditMode] = useState(false)

  // History for back navigation
  const [previousImageId, setPreviousImageId] = useState<string | null>(null)

  // Active learning state
  const [prioritize, setPrioritize] = useState(false)
  const [confidenceScore, setConfidenceScore] = useState<number | null>(null)

  // Preload queue — up to 3 images buffered ahead so "next" is instant
  type PreloadedEntry = { image: ImageData; annotations: BboxAnnotation[]; confidenceScore?: number }
  const [preloadQueue, setPreloadQueue] = useState<PreloadedEntry[]>([])

  // Session stats
  const [sessionStart] = useState<number>(Date.now())
  const [sessionCount, setSessionCount] = useState(0)
  const [sessionTimes, setSessionTimes] = useState<number[]>([])
  const [imageStartTime, setImageStartTime] = useState<number>(Date.now())

  // Ref to track latest annotations for async callbacks (avoids stale closures)
  const annotationsRef = useRef(annotations)
  annotationsRef.current = annotations

  // Faction filter state
  const [selectedFaction, setSelectedFaction] = useState<string | null>(null)

  // Fetch progress on mount
  useEffect(() => {
    fetchProgress()
  }, [])

  // Fetch annotation progress
  const fetchProgress = async () => {
    try {
      setFetchingProgress(true)
      const response = await fetch(`${API_BASE}/api/annotate/progress`)
      const data = await response.json()

      if (data.success) {
        setProgress(data.data.progress)
      }
    } catch (err) {
      console.error('Failed to fetch progress:', err)
    } finally {
      setFetchingProgress(false)
    }
  }

  // Load next image. factionOverride lets callers pass a faction directly
  // (e.g. when clicking a faction card, before state has updated).
  const loadNextImage = async (factionOverride?: string | null, extraExclude?: string) => {
    // Remember current image for back navigation
    if (currentImage) {
      setPreviousImageId(currentImage.imageId)
    }

    setError(null)
    setSuccess(null)

    const faction = factionOverride !== undefined ? factionOverride : selectedFaction

    // Use preloaded image if available, not the same as current, and no faction override
    const preloadedImage = preloadQueue[0]
    if (preloadedImage && factionOverride === undefined && preloadedImage.image.imageId !== currentImage?.imageId) {
      setCurrentImage(preloadedImage.image)
      setAnnotations(preloadedImage.annotations)
      setConfidenceScore(preloadedImage.confidenceScore ?? null)
      setPredictions([])
      setProcessedPredictions([])
      setValidationMode(false)
      setHighlightedPrediction(null)
      setPreloadQueue([])
      return
    }
    // Discard stale preload (same image as current — was fetched before save completed)
    setPreloadQueue([])

    setLoading(true)

    try {
      // Get next image metadata
      const params = new URLSearchParams()
      if (prioritize) params.set('prioritize', 'true')
      if (faction) params.set('faction', faction)
      if (annotatorName) params.set('userId', annotatorName)
      const excludeIds = extraExclude ? new Set([...skippedIds, extraExclude]) : skippedIds
      if (excludeIds.size > 0) params.set('exclude', Array.from(excludeIds).join(','))
      const qs = params.toString()
      const url = `${API_BASE}/api/annotate/next${qs ? '?' + qs : ''}`
      const response = await fetch(url)
      const data = await response.json()

      if (!data.success || !data.data.image) {
        setError('No more images to annotate!')
        setLoading(false)
        return
      }

      const imageInfo = data.data.image
      setConfidenceScore(imageInfo.confidenceScore ?? null)

      // /next now returns full image data inline (base64, dimensions, annotation)
      // so no second fetch is needed — saves one round trip over ngrok.
      let newAnnotations: BboxAnnotation[] = []

      if (data.data.annotation?.annotations) {
        newAnnotations = data.data.annotation.annotations.map((ann: any) => ({
          id: ann.id,
          x: ann.modelBbox.x,
          y: ann.modelBbox.y,
          width: ann.modelBbox.width,
          height: ann.modelBbox.height,
          classLabel: ann.classLabel,
          baseBbox: ann.baseBbox
        }))
      }

      setCurrentImage(imageInfo)
      setAnnotations(newAnnotations)
      setPredictions([])
      setProcessedPredictions([])
      setValidationMode(false)
      setHighlightedPrediction(null)
    } catch (err: any) {
      setError(`Failed to load image: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  // Load a specific image by ID (for editing previously annotated images)
  const loadSpecificImage = async (imageId: string) => {
    setLoading(true)
    setError(null)
    setSuccess(null)
    setEditMode(true)

    try {
      const imageResponse = await fetch(`${API_BASE}/api/annotate/image/${imageId}`)
      const imageData = await imageResponse.json()

      if (imageData.success) {
        let newAnnotations: BboxAnnotation[] = []

        if (imageData.data.annotation && imageData.data.annotation.annotations) {
          newAnnotations = imageData.data.annotation.annotations.map((ann: any) => ({
            id: ann.id,
            x: ann.modelBbox.x,
            y: ann.modelBbox.y,
            width: ann.modelBbox.width,
            height: ann.modelBbox.height,
            classLabel: ann.classLabel,
            baseBbox: ann.baseBbox
          }))
        }

        setCurrentImage(imageData.data.image)
        setAnnotations(newAnnotations)
        setPredictions([])
        setProcessedPredictions([])
        setValidationMode(false)
        setHighlightedPrediction(null)
        setSuccess(`Editing previously annotated image — Save to update`)
      } else {
        setError(`Image not found: ${imageId}`)
      }
    } catch (err: any) {
      setError(`Failed to load image: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  // Go back to previous image
  const goBack = () => {
    if (!previousImageId) return
    loadSpecificImage(previousImageId)
    setPreviousImageId(null)
  }

  // Load specific image when editImageId prop is provided
  useEffect(() => {
    if (editImageId) {
      loadSpecificImage(editImageId)
    }
  }, [editImageId])

  // Auto-load DINO proposals when navigating to a new unannotated image
  useEffect(() => {
    if (!currentImage || loading || editMode) return
    // Only auto-load if the image has no existing annotations
    if (annotations.length > 0) return

    const abortController = new AbortController()

    const loadProposals = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/annotate/proposals/${currentImage.imageId}`, {
          signal: abortController.signal,
        })
        const data = await res.json()
        // Skip if user drew boxes while we were fetching
        if (annotationsRef.current.length > 0) return
        if (data.success && data.data.predictions?.length > 0) {
          const factionLabel = remapFaction(currentImage.faction)
          const proposed: BboxAnnotation[] = data.data.predictions.map((pred: any, idx: number) => ({
            id: `dino_${idx}_${Date.now()}`,
            x: pred.x,
            y: pred.y,
            width: pred.width,
            height: pred.height,
            classLabel: factionLabel,
            confidence: pred.confidence,
            isPrediction: true,
            validated: false,
          }))
          setPredictions(proposed)
          setAnnotations(proposed)
          setValidationMode(true)
          setSuccess(`🤖 DINO found ${proposed.length} miniatures! Resize boxes to fit tightly, then validate.`)
        }
      } catch {
        // Aborted, network error, or proposals unavailable — no-op
      }
    }
    loadProposals()

    return () => abortController.abort()
  }, [currentImage?.imageId])

  // Prefetch next image while user annotates current one
  const prefetchNextImage = async () => {
    try {
      const params = new URLSearchParams()
      if (prioritize) params.set('prioritize', 'true')
      if (selectedFaction) params.set('faction', selectedFaction)
      if (annotatorName) params.set('userId', annotatorName)
      const qs = params.toString()
      const url = `${API_BASE}/api/annotate/next${qs ? '?' + qs : ''}`
      const response = await fetch(url)
      const data = await response.json()

      if (!data.success || !data.data.image) return

      const imageInfo = data.data.image
      let newAnnotations: BboxAnnotation[] = []
      if (data.data.annotation?.annotations) {
        newAnnotations = data.data.annotation.annotations.map((ann: any) => ({
          id: ann.id,
          x: ann.modelBbox.x,
          y: ann.modelBbox.y,
          width: ann.modelBbox.width,
          height: ann.modelBbox.height,
          classLabel: ann.classLabel,
          baseBbox: ann.baseBbox
        }))
      }

      setPreloadQueue(prev => [...prev, {
        image: imageInfo,
        annotations: newAnnotations,
        confidenceScore: imageInfo.confidenceScore
      }])
    } catch {
      // Silent fail — prefetch is optional
    }
  }

  // Track image start time when a new image loads
  useEffect(() => {
    if (currentImage) {
      setImageStartTime(Date.now())
    }
  }, [currentImage?.imageId])

  // Save current annotations
  const saveAnnotations = async () => {
    if (!currentImage) return

    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      // Accepted predictions now stay in `annotations` (as isAccepted:true), so just use annotations directly.
      // processedPredictions still holds rejected/redrawn for training metadata.
      const rejectedPredictions = processedPredictions.filter(p => p.validationAction === 'rejected')
      const redrawnPredictions = processedPredictions.filter(p => p.validationAction === 'redrawn')

      // All boxes to save: manual annotations + accepted AI predictions + unconfirmed predictions.
      // Unconfirmed DINO/YOLO predictions are treated as accepted (user didn't reject them).
      const allAnnotations = annotations

      // Convert BboxAnnotator format to backend format
      const annotationData = {
        imageId: currentImage.imageId,
        imagePath: currentImage.imagePath,
        faction: currentImage.faction,
        source: currentImage.source,
        width: currentImage.width || 0,
        height: currentImage.height || 0,
        annotations: allAnnotations.map(ann => ({
          id: ann.id,
          modelBbox: {
            x: ann.x,
            y: ann.y,
            width: ann.width,
            height: ann.height
          },
          baseBbox: ann.baseBbox,
          classLabel: ann.classLabel,
          // Include AI metadata for training
          confidence: ann.confidence,
          validationAction: ann.validationAction,
          originalPrediction: ann.originalPrediction
        })),
        // Store rejected predictions separately for hard negative mining
        rejectedPredictions: rejectedPredictions.map(ann => ({
          id: ann.id,
          modelBbox: {
            x: ann.x,
            y: ann.y,
            width: ann.width,
            height: ann.height
          },
          classLabel: ann.classLabel,
          confidence: ann.confidence
        })),
        // Store redrawn predictions to track where AI was wrong
        redrawnPredictions: redrawnPredictions.map(ann => ({
          id: ann.id,
          modelBbox: {
            x: ann.x,
            y: ann.y,
            width: ann.width,
            height: ann.height
          },
          classLabel: ann.classLabel,
          confidence: ann.confidence
        })),
        annotatedAt: new Date().toISOString(),
        annotatedBy: annotatorName || 'anonymous'
      }

      const response = await fetch(`${API_BASE}/api/annotate/save`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(annotationData)
      })

      const data = await response.json()

      if (data.success) {
        // Check for warnings (save succeeded but with warnings)
        if (data.warnings && data.warnings.length > 0) {
          setQualityWarnings(data.warnings)
          setQualityErrors([])
          setShowQualityModal(true)
        }

        const totalSaved = allAnnotations.length
        const rejectedCount = rejectedPredictions.length
        const redrawnCount = redrawnPredictions.length
        setSuccess(`✅ Saved ${totalSaved} annotations! (${rejectedCount} rejected, ${redrawnCount} redrawn for training)`)

        // Track session stats
        const elapsed = (Date.now() - imageStartTime) / 1000
        setSessionCount(prev => prev + 1)
        setSessionTimes(prev => [...prev.slice(-49), elapsed])

        // Prefetch now — current image is saved so /api/annotate/next will skip it
        prefetchNextImage()

        // Update progress and load next image
        await fetchProgress()
        if (editMode) {
          setEditMode(false)
          onEditComplete?.()
        }
        setTimeout(() => {
          loadNextImage()
        }, 300)
      } else {
        // Check for validation errors
        if (data.errors && data.warnings) {
          // Validation failed - show modal
          setQualityErrors(data.errors)
          setQualityWarnings(data.warnings)
          setShowQualityModal(true)
          setError(null) // Clear generic error since we're showing detailed modal
        } else {
          // Other error
          setError(`Failed to save: ${data.error?.message || 'Unknown error'}`)
        }
      }
    } catch (err: any) {
      setError(`Failed to save: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  // Get AI predictions for the current image.
  // Tries pre-computed DINO proposals first (instant), falls back to live YOLO inference.
  const getAIPredictions = async () => {
    if (!currentImage) return

    setPredicting(true)
    setError(null)

    try {
      // Try DINO proposals first (pre-computed, instant)
      let predictions: any[] = []
      let source = 'yolo'

      try {
        const proposalRes = await fetch(`${API_BASE}/api/annotate/proposals/${currentImage.imageId}`)
        const proposalData = await proposalRes.json()
        if (proposalData.success && proposalData.data.predictions?.length > 0) {
          predictions = proposalData.data.predictions
          source = 'grounding_dino'
        }
      } catch {
        // Proposals endpoint unavailable, fall through to YOLO
      }

      // Fall back to YOLO if no DINO proposals
      if (predictions.length === 0) {
        const response = await fetch(`${API_BASE}/api/annotate/predict/${currentImage.imageId}`)
        const data = await response.json()
        if (data.success) {
          predictions = data.data.predictions || []
          source = 'yolo'
        } else {
          setError(`Failed to get predictions: ${data.error?.message || 'Unknown error'}`)
          return
        }
      }

      if (predictions.length > 0) {
        // Use the image's faction as classLabel for DINO proposals (they come as 'miniature')
        const factionLabel = remapFaction(currentImage.faction)

        const predictedAnnotations: BboxAnnotation[] = predictions.map((pred: any, idx: number) => ({
          id: `pred_${idx}_${Date.now()}`,
          x: pred.x,
          y: pred.y,
          width: pred.width,
          height: pred.height,
          classLabel: source === 'grounding_dino' ? factionLabel : pred.classLabel,
          confidence: pred.confidence,
          isPrediction: true,
          validated: false
        }))

        setPredictions(predictedAnnotations)
        setAnnotations(predictedAnnotations)
        setValidationMode(true)
        const sourceLabel = source === 'grounding_dino' ? 'DINO' : 'YOLO'
        setSuccess(`🤖 ${sourceLabel} found ${predictedAnnotations.length} miniatures! Resize boxes to fit tightly, then validate.`)
      } else {
        setSuccess('No AI proposals found for this image. Draw boxes manually.')
      }
    } catch (err: any) {
      setError(`Failed to get predictions: ${err.message}`)
    } finally {
      setPredicting(false)
    }
  }

  // Processed predictions storage (for training data)
  const [processedPredictions, setProcessedPredictions] = useState<BboxAnnotation[]>([])

  // Accept a prediction (mark as correct — turns green, stays on canvas)
  const acceptPrediction = (id: string) => {
    // Update the box in-place: clear isPrediction, set isAccepted so it renders green
    setAnnotations(prev => prev.map(ann =>
      ann.id === id
        ? { ...ann, isPrediction: false, isAccepted: true, validated: true, validationAction: 'accepted', originalPrediction: true }
        : ann
    ))
    setPredictions(prev => prev.filter(p => p.id !== id))
    setHighlightedPrediction(null)
  }

  // Reject a prediction (store as rejected for hard negative mining)
  const rejectPrediction = (id: string) => {
    const prediction = annotations.find(ann => ann.id === id)
    if (prediction) {
      // Store rejected prediction for training (hard negative mining)
      setProcessedPredictions(prev => [...prev, {
        ...prediction,
        validated: false,
        isPrediction: false,
        validationAction: 'rejected',
        originalPrediction: true
      }])
    }
    // Remove from display
    setAnnotations(prev => prev.filter(ann => ann.id !== id))
    setPredictions(prev => prev.filter(p => p.id !== id))
    setHighlightedPrediction(null)
  }

  // Enter redraw mode for a prediction (remove box, user draws new one)
  const redrawPrediction = (id: string) => {
    const prediction = annotations.find(ann => ann.id === id)
    if (prediction) {
      // Store as redrawn for training data
      setProcessedPredictions(prev => [...prev, {
        ...prediction,
        validated: false,
        isPrediction: false,
        validationAction: 'redrawn',
        originalPrediction: true
      }])
    }
    // Remove from display
    setAnnotations(prev => prev.filter(ann => ann.id !== id))
    setPredictions(prev => prev.filter(p => p.id !== id))
    setHighlightedPrediction(null)
    setSuccess('Draw the correct bounding box manually')
  }

  // Accept all remaining predictions and save
  const acceptAllPredictions = async () => {
    if (!currentImage) return

    setSaving(true)

    // Accept all remaining pending predictions — flip them green in-place
    setAnnotations(prev => prev.map(ann =>
      ann.isPrediction
        ? { ...ann, isPrediction: false, isAccepted: true, validated: true, validationAction: 'accepted' as const, originalPrediction: true }
        : ann
    ))
    setPredictions([])

    const rejectedPredictions = processedPredictions.filter(p => p.validationAction === 'rejected')
    const redrawnPredictions = processedPredictions.filter(p => p.validationAction === 'redrawn')

    // All boxes: manual + everything now accepted (isPrediction cleared above)
    const allAnnotations = annotations.map(ann =>
      ann.isPrediction
        ? { ...ann, isPrediction: false, isAccepted: true, validated: true, validationAction: 'accepted' as const, originalPrediction: true }
        : ann
    )

    try {
      const annotationData = {
        imageId: currentImage.imageId,
        imagePath: currentImage.imagePath,
        faction: currentImage.faction,
        source: currentImage.source,
        width: currentImage.width || 0,
        height: currentImage.height || 0,
        annotations: allAnnotations.map(ann => ({
          id: ann.id,
          modelBbox: { x: ann.x, y: ann.y, width: ann.width, height: ann.height },
          baseBbox: ann.baseBbox,
          classLabel: ann.classLabel,
          confidence: ann.confidence,
          validationAction: ann.validationAction,
          originalPrediction: ann.originalPrediction
        })),
        rejectedPredictions: rejectedPredictions.map(ann => ({
          id: ann.id,
          modelBbox: { x: ann.x, y: ann.y, width: ann.width, height: ann.height },
          classLabel: ann.classLabel,
          confidence: ann.confidence
        })),
        redrawnPredictions: redrawnPredictions.map(ann => ({
          id: ann.id,
          modelBbox: { x: ann.x, y: ann.y, width: ann.width, height: ann.height },
          classLabel: ann.classLabel,
          confidence: ann.confidence
        })),
        annotatedAt: new Date().toISOString(),
        annotatedBy: annotatorName || 'anonymous'
      }

      const response = await fetch(`${API_BASE}/api/annotate/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(annotationData)
      })

      const data = await response.json()

      if (data.success) {
        setSuccess(`✅ Saved ${allAnnotations.length} annotations! Loading next...`)
        await fetchProgress()
        setTimeout(() => loadNextImage(), 300)
      } else {
        setError(`Failed to save: ${data.error?.message || 'Unknown error'}`)
      }
    } catch (err: any) {
      setError(`Failed to save: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  // Reject all remaining predictions
  const rejectAllPredictions = () => {
    const remaining = [...predictions]
    for (const pred of remaining) {
      rejectPrediction(pred.id)
    }
  }

  // Accept predictions above a confidence threshold (default 80%)
  const acceptHighConfidencePredictions = (threshold = 0.8) => {
    const remaining = [...predictions]
    for (const pred of remaining) {
      if ((pred.confidence || 0) >= threshold) {
        acceptPrediction(pred.id)
      }
    }
  }

  // Ref to hold latest prediction action functions (avoids stale closures in keyboard handler)
  const predictionActionsRef = useRef({ acceptPrediction, rejectPrediction, redrawPrediction, acceptAllPredictions })
  predictionActionsRef.current = { acceptPrediction, rejectPrediction, redrawPrediction, acceptAllPredictions }

  // Track images skipped this session so the backend won't re-serve them
  const [skippedIds, setSkippedIds] = useState<Set<string>>(new Set())

  // Skip current image without saving anything — image stays unannotated
  const skipImage = async () => {
    if (!currentImage) return

    setError(null)
    setSuccess(null)
    const skippedId = currentImage.imageId
    setSkippedIds(prev => new Set(prev).add(skippedId))
    setAnnotations([])
    setPredictions([])
    setProcessedPredictions([])
    setValidationMode(false)
    await loadNextImage(undefined, skippedId)
  }

  // Flag image as permanently unusable
  const flagImage = async () => {
    if (!currentImage) return

    setSaving(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE}/api/annotate/flag`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ imageId: currentImage.imageId, reason: 'unusable' })
      })
      const data = await response.json()

      if (data.success) {
        setSuccess('🚫 Image flagged as unusable — loading next...')
        setAnnotations([])
        await fetchProgress()
        setTimeout(() => loadNextImage(), 300)
      } else {
        setError(`Failed to flag: ${data.error?.message || 'Unknown error'}`)
      }
    } catch (err: any) {
      setError(`Failed to flag: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  // Keyboard shortcuts for AI prediction validation panel
  useEffect(() => {
    if (predictions.length === 0) return

    const handlePredictionKeys = (e: KeyboardEvent) => {
      // Don't interfere if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) {
        return
      }

      // Tab / Shift+Tab — cycle through predictions
      if (e.key === 'Tab') {
        e.preventDefault()
        if (predictions.length === 0) return

        const currentIdx = highlightedPrediction
          ? predictions.findIndex(p => p.id === highlightedPrediction)
          : -1

        let nextIdx: number
        if (e.shiftKey) {
          nextIdx = currentIdx <= 0 ? predictions.length - 1 : currentIdx - 1
        } else {
          nextIdx = currentIdx >= predictions.length - 1 ? 0 : currentIdx + 1
        }
        setHighlightedPrediction(predictions[nextIdx].id)
        return
      }

      // Read latest action functions from ref to avoid stale closures
      const actions = predictionActionsRef.current

      // A — Accept highlighted prediction
      if (e.key === 'a' || e.key === 'A') {
        if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault()
          if (highlightedPrediction) {
            actions.acceptPrediction(highlightedPrediction)
          }
        }
        return
      }

      // W — Mark highlighted prediction as Wrong
      if (e.key === 'w' || e.key === 'W') {
        e.preventDefault()
        if (highlightedPrediction) {
          actions.rejectPrediction(highlightedPrediction)
        }
        return
      }

      // R — Mark highlighted prediction for Redraw
      if (e.key === 'r' || e.key === 'R') {
        if (!e.ctrlKey && !e.metaKey) {
          e.preventDefault()
          if (highlightedPrediction) {
            actions.redrawPrediction(highlightedPrediction)
          }
        }
        return
      }

      // Enter — Accept all remaining predictions and save
      if (e.key === 'Enter') {
        e.preventDefault()
        actions.acceptAllPredictions()
        return
      }
    }

    window.addEventListener('keydown', handlePredictionKeys)
    return () => window.removeEventListener('keydown', handlePredictionKeys)
  }, [predictions, highlightedPrediction])

  return (
    <div className="annotation-interface" style={{ padding: '0.5rem', margin: '0 auto' }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '2rem',
        padding: '1.5rem',
        backgroundColor: '#1a1a1a',
        borderRadius: '12px',
        border: '1px solid #333'
      }}>
        <div style={{ flex: 1 }}>
          <h1 style={{ margin: 0, fontSize: '2rem', color: '#fff' }}>
            🎨 Training Data Annotation
          </h1>
          {progress && (
            <>
              <div style={{ marginTop: '1rem', fontSize: '1.2rem', color: '#fff', fontWeight: 'bold' }}>
                <span style={{ color: '#10b981', fontSize: '2rem' }}>{progress.annotatedImages.toLocaleString()}</span>
                <span style={{ color: '#666', margin: '0 0.5rem' }}>/</span>
                <span style={{ color: '#aaa' }}>{progress.totalImages.toLocaleString()}</span>
                <span style={{ color: '#666', marginLeft: '1rem', fontSize: '1rem' }}>
                  ({progress.percentComplete.toFixed(3)}% complete)
                </span>
              </div>
              <div style={{ marginTop: '0.75rem', height: '8px', backgroundColor: '#333', borderRadius: '4px', overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  width: `${progress.percentComplete}%`,
                  backgroundColor: '#10b981',
                  transition: 'width 0.5s ease',
                  boxShadow: '0 0 10px rgba(16, 185, 129, 0.5)'
                }} />
              </div>
            </>
          )}
        </div>

        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          {/* Prioritize toggle */}
          <label style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            cursor: 'pointer',
            padding: '0.5rem 1rem',
            backgroundColor: prioritize ? '#7c3aed30' : '#1a1a1a',
            border: prioritize ? '1px solid #7c3aed' : '1px solid #333',
            borderRadius: '8px',
            fontSize: '0.85rem',
            color: prioritize ? '#a78bfa' : '#888',
            transition: 'all 0.2s'
          }}>
            <input
              type="checkbox"
              checked={prioritize}
              onChange={e => setPrioritize(e.target.checked)}
              style={{ accentColor: '#7c3aed' }}
            />
            Prioritize by confidence
          </label>

          {/* Confidence badge */}
          {confidenceScore !== null && prioritize && (
            <span style={{
              padding: '0.4rem 0.8rem',
              backgroundColor: confidenceScore < 0.3 ? '#dc262640' : confidenceScore < 0.6 ? '#f59e0b40' : '#05966940',
              color: confidenceScore < 0.3 ? '#fca5a5' : confidenceScore < 0.6 ? '#fcd34d' : '#6ee7b7',
              borderRadius: '6px',
              fontSize: '0.8rem',
              fontWeight: 'bold'
            }}>
              Conf: {(confidenceScore * 100).toFixed(0)}%
            </span>
          )}

          <button
            onClick={fetchProgress}
            disabled={fetchingProgress}
            style={{
              padding: '0.75rem 1.5rem',
              backgroundColor: '#374151',
              color: '#fff',
              border: '1px solid #4b5563',
              borderRadius: '8px',
              fontSize: '0.9rem',
              cursor: fetchingProgress ? 'not-allowed' : 'pointer',
              opacity: fetchingProgress ? 0.5 : 1,
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              if (!fetchingProgress) {
                e.currentTarget.style.backgroundColor = '#4b5563'
              }
            }}
            onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#374151'}
          >
            {fetchingProgress ? '⏳ Updating...' : '🔄 Refresh Progress'}
          </button>
          {!currentImage && (
            <button
              onClick={() => loadNextImage()}
              disabled={loading}
              style={{
                padding: '1rem 2rem',
                backgroundColor: '#2563eb',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                fontSize: '1rem',
                fontWeight: 'bold',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.5 : 1
              }}
            >
              {loading ? 'Loading...' : 'Start Annotating'}
            </button>
          )}
        </div>
      </div>

      {/* Progress Stats */}
      {progress && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem',
          marginBottom: '2rem'
        }}>
          {Object.entries(progress.byFaction)
            .sort((a, b) => b[1].total - a[1].total)
            .map(([faction, stats]) => {
              const isSelected = selectedFaction === faction
              const isComplete = stats.annotated >= stats.total
              return (
              <div
                key={faction}
                onClick={() => {
                  const newFaction = isSelected ? null : faction
                  setSelectedFaction(newFaction)
                  loadNextImage(newFaction)
                }}
                style={{
                  padding: '1rem',
                  backgroundColor: isSelected ? '#1a2a1a' : '#1a1a1a',
                  borderRadius: '8px',
                  border: isSelected ? '2px solid #10b981' : '1px solid #333',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  opacity: isComplete && !isSelected ? 0.6 : 1
                }}
              >
                <div style={{
                  color: isSelected ? '#10b981' : '#aaa',
                  fontSize: '0.8rem',
                  marginBottom: '0.5rem',
                  textTransform: 'capitalize',
                  fontWeight: isSelected ? 'bold' : 'normal'
                }}>
                  {faction.replace(/_/g, ' ')}
                  {isSelected && ' ●'}
                </div>
                <div style={{ color: '#fff', fontSize: '1.2rem', fontWeight: 'bold' }}>
                  {stats.annotated} / {stats.total}
                </div>
                <div style={{ marginTop: '0.5rem', height: '4px', backgroundColor: '#333', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${(stats.annotated / stats.total) * 100}%`,
                    backgroundColor: isComplete ? '#059669' : '#10b981',
                    transition: 'width 0.3s'
                  }} />
                </div>
              </div>
              )
            })}
        </div>
      )}

      {/* Selected Faction Indicator */}
      {selectedFaction && (
        <div style={{
          padding: '0.75rem 1rem',
          backgroundColor: '#1a2a1a',
          borderRadius: '8px',
          border: '1px solid #10b981',
          marginBottom: '1rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span style={{ color: '#10b981', fontSize: '0.9rem' }}>
            Filtering: <strong style={{ textTransform: 'capitalize' }}>{selectedFaction.replace(/_/g, ' ')}</strong>
          </span>
          <button
            onClick={() => setSelectedFaction(null)}
            style={{
              padding: '0.3rem 0.75rem',
              backgroundColor: '#374151',
              color: '#aaa',
              border: '1px solid #4b5563',
              borderRadius: '4px',
              fontSize: '0.8rem',
              cursor: 'pointer'
            }}
          >
            Clear filter
          </button>
        </div>
      )}

      {/* Session Stats Bar */}
      {sessionCount > 0 && (
        <div style={{
          display: 'flex',
          gap: '2rem',
          padding: '0.5rem 1rem',
          backgroundColor: '#1e293b',
          borderRadius: '6px',
          marginBottom: '1rem',
          fontSize: '0.85rem',
          color: '#94a3b8',
          justifyContent: 'center'
        }}>
          <span>Session: <strong style={{ color: '#10b981' }}>{sessionCount}</strong> images</span>
          <span>Duration: <strong style={{ color: '#60a5fa' }}>{Math.floor((Date.now() - sessionStart) / 60000)}m</strong></span>
          <span>Avg: <strong style={{ color: '#f59e0b' }}>
            {sessionTimes.length > 0
              ? `${Math.round(sessionTimes.reduce((a, b) => a + b, 0) / sessionTimes.length)}s`
              : '—'}
          </strong>/image</span>
        </div>
      )}

      {/* Error/Success Messages */}
      {error && (
        <div style={{
          padding: '1rem',
          backgroundColor: '#dc2626',
          color: '#fff',
          borderRadius: '8px',
          marginBottom: '1rem'
        }}>
          ❌ {error}
        </div>
      )}

      {success && (
        <div style={{
          padding: '1rem',
          backgroundColor: '#059669',
          color: '#fff',
          borderRadius: '8px',
          marginBottom: '1rem'
        }}>
          {success}
        </div>
      )}

      {/* Edit Mode Banner */}
      {editMode && currentImage && (
        <div style={{
          padding: '0.75rem 1rem',
          backgroundColor: '#92400e',
          color: '#fff',
          borderRadius: '8px',
          marginBottom: '1rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontWeight: 'bold'
        }}>
          <span>Editing previously annotated image — Save to update</span>
          <button
            onClick={() => { setEditMode(false); onEditComplete?.(); loadNextImage() }}
            style={{
              padding: '0.4rem 0.75rem',
              backgroundColor: '#78350f',
              color: '#fff',
              border: '1px solid #b45309',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.85rem'
            }}
          >
            Cancel Edit
          </button>
        </div>
      )}

      {/* Current Image Info */}
      {currentImage && (
        <div style={{
          padding: '1rem',
          backgroundColor: '#1a1a1a',
          borderRadius: '8px',
          border: '1px solid #333',
          marginBottom: '1rem'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ color: '#aaa', fontSize: '0.8rem' }}>Current Image:</div>
              <div style={{ color: '#fff', fontSize: '1rem', marginTop: '0.25rem' }}>
                <span style={{ color: '#10b981', textTransform: 'capitalize' }}>
                  {remapFaction(currentImage.faction).replace(/_/g, ' ')}
                </span>
                {' '} / {currentImage.source}
                {' '} / {currentImage.width}x{currentImage.height}
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <span style={{ padding: '0.5rem 1rem', backgroundColor: '#2a2a2a', borderRadius: '4px', fontSize: '0.9rem', color: '#aaa' }}>
                {annotations.length} annotations
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Annotator */}
      {currentImage && currentImage.imageBase64 && currentImage.width && currentImage.height && (
        <div style={{ marginBottom: '1rem', width: '100%' }}>
          <BboxAnnotator
            key={currentImage.imageId}  // Force re-mount when image changes
            imageUrl={currentImage.imageBase64}
            imageWidth={currentImage.width}
            imageHeight={currentImage.height}
            onAnnotationsChange={(newAnns: BboxAnnotation[]) => {
              setAnnotations(newAnns)
              // Sync predictions panel: remove entries whose boxes were deleted on canvas
              const annIds = new Set(newAnns.map(a => a.id))
              setPredictions(prev => prev.filter(p => annIds.has(p.id)))
            }}
            classLabels={[remapFaction(currentImage.faction)]}  // Use faction as default class
            defaultClass={remapFaction(currentImage.faction)}
            initialAnnotations={annotations}  // Pre-populate with AI suggestions or existing annotations
            onSaveRequested={saveAnnotations}  // Keyboard shortcut: S
            onSkipRequested={skipImage}  // Keyboard shortcut: K
            onFlagRequested={flagImage}  // Keyboard shortcut: X
            onBackRequested={goBack}  // Keyboard shortcut: B
            highlightedId={highlightedPrediction}  // Highlight box from validation panel hover
            onBoxSelected={setHighlightedPrediction}  // Sync selection to validation panel
          />
        </div>
      )}

      {/* AI Prediction Validation Panel */}
      {currentImage && predictions.length > 0 && (
        <div style={{
          padding: '1.5rem',
          backgroundColor: '#1e293b',
          borderRadius: '8px',
          border: '2px solid #3b82f6',
          marginBottom: '1rem'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h3 style={{ margin: 0, color: '#fff' }}>🤖 AI Predictions - Validate Each Box</h3>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                onClick={() => acceptHighConfidencePredictions()}
                style={{
                  padding: '0.4rem 0.75rem',
                  backgroundColor: '#0d9488',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  cursor: 'pointer'
                }}
                title="Accept predictions with >80% confidence"
              >
                ✓ Accept High Conf
              </button>
              <button
                onClick={acceptAllPredictions}
                style={{
                  padding: '0.4rem 0.75rem',
                  backgroundColor: '#059669',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  fontWeight: 'bold'
                }}
                title="Accept all remaining predictions and save (Enter)"
              >
                ✓ Accept All
              </button>
              <button
                onClick={rejectAllPredictions}
                style={{
                  padding: '0.4rem 0.75rem',
                  backgroundColor: '#dc2626',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  cursor: 'pointer'
                }}
                title="Reject all remaining predictions"
              >
                ✗ Reject All
              </button>
            </div>
          </div>

          {/* Keyboard shortcut legend */}
          <div style={{
            display: 'flex',
            gap: '1rem',
            marginBottom: '0.75rem',
            padding: '0.5rem 0.75rem',
            backgroundColor: '#0f172a',
            borderRadius: '4px',
            fontSize: '0.75rem',
            color: '#64748b',
            flexWrap: 'wrap'
          }}>
            <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>Tab</kbd> cycle</span>
            <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>A</kbd> accept</span>
            <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>W</kbd> wrong</span>
            <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>R</kbd> redraw</span>
            <span><kbd style={{ color: '#94a3b8', backgroundColor: '#1e293b', padding: '1px 5px', borderRadius: '3px', border: '1px solid #334155' }}>Enter</kbd> accept all + save</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {predictions.map((pred, idx) => {
              const isHighlighted = pred.id === highlightedPrediction
              return (
                <div
                  key={pred.id}
                  onMouseEnter={() => setHighlightedPrediction(pred.id)}
                  onMouseLeave={() => setHighlightedPrediction(null)}
                  onClick={() => setHighlightedPrediction(pred.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '1rem',
                    padding: '0.75rem 1rem',
                    backgroundColor: isHighlighted ? '#1e3a5f' : '#0f172a',
                    borderRadius: '6px',
                    border: isHighlighted ? '2px solid #00ffff' : '1px solid #334155',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease'
                  }}
                >
                  <span style={{
                    color: isHighlighted ? '#00ffff' : '#94a3b8',
                    fontWeight: 'bold',
                    minWidth: '30px',
                    fontSize: '1.1rem'
                  }}>
                    #{idx + 1}
                  </span>
                  <span style={{ color: '#fff', flex: 1 }}>
                    {pred.classLabel.replace(/_/g, ' ')}
                    <span style={{ color: '#64748b', marginLeft: '0.5rem' }}>
                      ({((pred.confidence || 0) * 100).toFixed(0)}% conf)
                    </span>
                  </span>

                  {/* Green - Accept */}
                  <button
                    onClick={(e) => { e.stopPropagation(); acceptPrediction(pred.id); }}
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#059669',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '1rem',
                      cursor: 'pointer',
                      fontWeight: 'bold'
                    }}
                    title="Correct - Accept this box"
                  >
                    ✓ Correct
                  </button>

                  {/* Yellow - Redraw */}
                  <button
                    onClick={(e) => { e.stopPropagation(); redrawPrediction(pred.id); }}
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#eab308',
                      color: '#000',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '1rem',
                      cursor: 'pointer',
                      fontWeight: 'bold'
                    }}
                    title="Redraw - Delete and draw manually"
                  >
                    ✎ Redraw
                  </button>

                  {/* Red - Wrong */}
                  <button
                    onClick={(e) => { e.stopPropagation(); rejectPrediction(pred.id); }}
                    style={{
                      padding: '0.5rem 1rem',
                      backgroundColor: '#dc2626',
                      color: '#fff',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '1rem',
                      cursor: 'pointer',
                      fontWeight: 'bold'
                    }}
                    title="Wrong - Remove this box"
                  >
                    ✗ Wrong
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Action Buttons */}
      {currentImage && (
        <div style={{
          display: 'flex',
          gap: '1rem',
          justifyContent: 'center',
          padding: '1.5rem',
          backgroundColor: '#1a1a1a',
          borderRadius: '8px',
          border: '1px solid #333'
        }}>
          {/* Back Button */}
          <button
            onClick={goBack}
            disabled={!previousImageId || loading || saving}
            style={{
              padding: '1rem 1.5rem',
              backgroundColor: previousImageId ? '#4b5563' : '#1f2937',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '1rem',
              fontWeight: 'bold',
              cursor: !previousImageId || loading || saving ? 'not-allowed' : 'pointer',
              opacity: !previousImageId || loading || saving ? 0.3 : 1,
              transition: 'all 0.2s'
            }}
            title="Go back to previous image (B)"
          >
            ← Back (B)
          </button>

          {/* AI Predict Button */}
          <button
            onClick={getAIPredictions}
            disabled={loading || saving || predicting}
            style={{
              padding: '1rem 2rem',
              backgroundColor: '#7c3aed',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '1rem',
              fontWeight: 'bold',
              cursor: loading || saving || predicting ? 'not-allowed' : 'pointer',
              opacity: loading || saving || predicting ? 0.5 : 1,
              transition: 'all 0.2s'
            }}
          >
            {predicting ? '🔄 Predicting...' : '🤖 Get AI Suggestions'}
          </button>

          <button
            onClick={skipImage}
            disabled={loading || saving}
            style={{
              padding: '1rem 2rem',
              backgroundColor: '#6b7280',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '1rem',
              fontWeight: 'bold',
              cursor: loading || saving ? 'not-allowed' : 'pointer',
              opacity: loading || saving ? 0.5 : 1,
              transition: 'all 0.2s'
            }}
            onMouseEnter={(e) => {
              if (!loading && !saving) {
                e.currentTarget.style.backgroundColor = '#9ca3af'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#6b7280'
            }}
          >
            ⏭️ Skip (no annotation)
          </button>

          <button
            onClick={flagImage}
            disabled={loading || saving}
            style={{
              padding: '1rem 1.5rem',
              backgroundColor: '#92400e',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '1rem',
              fontWeight: 'bold',
              cursor: loading || saving ? 'not-allowed' : 'pointer',
              opacity: loading || saving ? 0.5 : 1,
              transition: 'all 0.2s'
            }}
            title="Flag as unusable — permanently remove from annotation queue (X)"
          >
            🚫 Flag Unusable (X)
          </button>

          <button
            onClick={saveAnnotations}
            disabled={loading || saving || annotations.length === 0}
            style={{
              padding: '1rem 3rem',
              backgroundColor: annotations.length > 0 ? '#059669' : '#6b7280',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '1rem',
              fontWeight: 'bold',
              cursor: loading || saving || annotations.length === 0 ? 'not-allowed' : 'pointer',
              opacity: loading || saving || annotations.length === 0 ? 0.5 : 1
            }}
          >
            {saving ? 'Saving...' : `💾 Save & Next (${annotations.length} annotations)`}
          </button>
        </div>
      )}

      {/* Instructions */}
      <div style={{
        marginTop: '2rem',
        padding: '1.5rem',
        backgroundColor: '#1a1a1a',
        borderRadius: '8px',
        border: '1px solid #333',
        color: '#aaa',
        fontSize: '0.9rem'
      }}>
        <div style={{ fontWeight: 'bold', color: '#fff', marginBottom: '1rem' }}>Instructions:</div>
        <ol style={{ margin: 0, paddingLeft: '1.5rem' }}>
          <li style={{ marginBottom: '0.5rem' }}>Click "Start Annotating" to load the first image</li>
          <li style={{ marginBottom: '0.5rem' }}>Click <strong style={{ color: '#7c3aed' }}>🤖 Get AI Suggestions</strong> to let the AI detect miniatures</li>
          <li style={{ marginBottom: '0.5rem' }}>Validate each AI prediction:
            <ul style={{ marginTop: '0.25rem' }}>
              <li><strong style={{ color: '#059669' }}>✓ Correct</strong> - Accept the box as-is (<strong>A</strong>)</li>
              <li><strong style={{ color: '#eab308' }}>✎ Redraw</strong> - Delete and draw manually (<strong>R</strong>)</li>
              <li><strong style={{ color: '#dc2626' }}>✗ Wrong</strong> - Remove the box (<strong>W</strong>)</li>
              <li><strong>Tab</strong> / <strong>Shift+Tab</strong> — cycle through predictions</li>
              <li><strong>Enter</strong> — accept all remaining + save</li>
            </ul>
          </li>
          <li style={{ marginBottom: '0.5rem' }}>Draw additional boxes manually if the AI missed any</li>
          <li style={{ marginBottom: '0.5rem' }}>Click "Save & Next" to save and continue (<strong>S</strong>)</li>
          <li>Click "Skip" for images without miniatures (<strong>K</strong>)</li>
          <li>Click "Flag Unusable" to permanently remove bad images (<strong>X</strong>)</li>
          <li>Click "Back" to return to the previous image (<strong>B</strong>)</li>
        </ol>
      </div>

      {/* Quality Issues Modal */}
      {showQualityModal && (
        <QualityIssuesModal
          errors={qualityErrors}
          warnings={qualityWarnings}
          onClose={() => setShowQualityModal(false)}
        />
      )}
    </div>
  )
}
