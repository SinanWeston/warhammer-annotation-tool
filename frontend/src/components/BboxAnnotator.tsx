/**
 * BboxAnnotator Component
 *
 * Interactive canvas for drawing and editing bounding boxes on images.
 * Used for creating YOLO training datasets.
 *
 * Features:
 * - Click and drag to draw new bboxes
 * - Click existing bbox to select/edit
 * - Delete key to remove selected bbox
 * - Label each bbox with a class name
 * - Export to YOLO format
 */

import { useState, useRef, useEffect } from 'react'
import { BboxAnnotation } from '../types'
import { screenToImage, scaleBbox, fitScale } from '../utils/coordinates'
import {
  AddModelBoxCommand,
  DeleteModelBoxCommand,
  ChangeClassCommand,
  ChangeUnitCommand,
  type BboxCommand,
} from '../commands'

interface BboxAnnotatorProps {
  imageUrl: string
  imageWidth: number
  imageHeight: number
  onAnnotationsChange: (annotations: BboxAnnotation[]) => void
  classLabels: string[]  // Available faction slugs (20 canonical)
  defaultClass?: string
  /** Per-faction unit lists keyed by faction slug. When provided, the
   *  picker below the canvas renders a unit dropdown scoped to the
   *  currently-selected bbox's `classLabel`. Optional — if absent, the
   *  UI degrades to faction-only (the pre-taxonomy behaviour). */
  unitsByFaction?: Record<string, Array<{ slug: string; name: string; category?: string }>>
  initialAnnotations?: BboxAnnotation[]  // Pre-populated annotations (e.g., from AI)
  onSaveRequested?: () => void  // Called when user presses save shortcut
  onSkipRequested?: () => void  // Called when user presses skip shortcut
  onFlagRequested?: () => void  // Called when user presses flag shortcut (X)
  onBackRequested?: () => void  // Called when user presses back shortcut (B)
  highlightedId?: string | null  // ID of box to highlight (from validation panel hover)
  onBoxSelected?: (id: string | null) => void  // Called when a box is selected/clicked
}

interface DrawingState {
  isDrawing: boolean
  startX: number
  startY: number
  currentX: number
  currentY: number
}

type ResizeHandle = 'nw' | 'ne' | 'sw' | 'se' | 'n' | 's' | 'e' | 'w'

interface ResizingState {
  isResizing: boolean
  boxId: string
  handle: ResizeHandle
  // Original box coords (image space) at drag start
  origX: number
  origY: number
  origWidth: number
  origHeight: number
}

const HANDLE_SIZE = 8 // px in screen space
const HANDLE_HIT_SIZE = 12 // px — slightly larger hit target for easier grabbing

/** Deterministic per-faction HSL colour. Same string → same hue across
 *  images + sessions, so the brain learns "space_marines = blue-ish" etc.
 *  70% saturation / 55% lightness reads well on the dark canvas bg. */
function factionStrokeColour(faction: string): string {
  let h = 0
  for (let i = 0; i < faction.length; i++) {
    h = (h * 31 + faction.charCodeAt(i)) >>> 0
  }
  return `hsl(${h % 360}, 70%, 55%)`
}

const HANDLE_CURSORS: Record<ResizeHandle, string> = {
  nw: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize', se: 'nwse-resize',
  n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize',
}

/**
 * Get the resize handle at the given screen position, if any.
 * Returns the handle type and the box ID, or null.
 */
function getHandleAtPoint(
  screenX: number,
  screenY: number,
  annotations: BboxAnnotation[],
  scale: number,
): { handle: ResizeHandle; boxId: string } | null {
  // Check in reverse order so topmost (last drawn) box wins
  for (let i = annotations.length - 1; i >= 0; i--) {
    const box = annotations[i]
    const sx = box.x * scale
    const sy = box.y * scale
    const sw = box.width * scale
    const sh = box.height * scale

    const handles: { handle: ResizeHandle; hx: number; hy: number }[] = [
      { handle: 'nw', hx: sx, hy: sy },
      { handle: 'ne', hx: sx + sw, hy: sy },
      { handle: 'sw', hx: sx, hy: sy + sh },
      { handle: 'se', hx: sx + sw, hy: sy + sh },
      { handle: 'n', hx: sx + sw / 2, hy: sy },
      { handle: 's', hx: sx + sw / 2, hy: sy + sh },
      { handle: 'w', hx: sx, hy: sy + sh / 2 },
      { handle: 'e', hx: sx + sw, hy: sy + sh / 2 },
    ]

    for (const h of handles) {
      if (Math.abs(screenX - h.hx) <= HANDLE_HIT_SIZE && Math.abs(screenY - h.hy) <= HANDLE_HIT_SIZE) {
        return { handle: h.handle, boxId: box.id }
      }
    }
  }
  return null
}

// ═══════════════════════════════════════════════════════════
// COMMAND PATTERN FOR UNDO/REDO
// ═══════════════════════════════════════════════════════════

// Command classes now live in ../commands/. The base interface is BboxCommand.

export default function BboxAnnotator({
  imageUrl,
  imageWidth,
  imageHeight,
  onAnnotationsChange,
  classLabels,
  defaultClass = 'miniature',
  unitsByFaction,
  initialAnnotations = [],
  onSaveRequested,
  onSkipRequested,
  onFlagRequested,
  onBackRequested,
  highlightedId,
  onBoxSelected
}: BboxAnnotatorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  // scrollContainerRef was declared but never read — removed in commit 11.

  const [annotations, setAnnotations] = useState<BboxAnnotation[]>(initialAnnotations)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [resizing, setResizing] = useState<ResizingState>({
    isResizing: false, boxId: '', handle: 'se', origX: 0, origY: 0, origWidth: 0, origHeight: 0
  })
  const [hoverCursor, setHoverCursor] = useState<string>('default')

  // Sync annotations when initialAnnotations changes (e.g., AI predictions loaded)
  useEffect(() => {
    setAnnotations(initialAnnotations)
  }, [initialAnnotations])

  const [drawing, setDrawing] = useState<DrawingState>({
    isDrawing: false,
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0
  })
  const [scale, setScale] = useState(1)  // Fit-to-container scale
  const [zoom, setZoom] = useState(1)    // User zoom level (CSS transform)
  const [currentClass, setCurrentClass] = useState(defaultClass)
  // Default unit_slug for newly-drawn bboxes. Mirrors `currentClass` —
  // when no bbox is selected, the unit picker writes here, and the next
  // bbox you draw inherits both faction + unit. Empty string = "no
  // default; new bboxes get unit_slug undefined" (the existing audit-
  // pile pattern).
  const [currentUnit, setCurrentUnit] = useState<string>('')
  const [imageLoaded, setImageLoaded] = useState(false)

  // Undo/Redo stacks
  const [undoStack, setUndoStack] = useState<BboxCommand[]>([])
  const [redoStack, setRedoStack] = useState<BboxCommand[]>([])

  // Execute a command and add to undo stack
  const executeCommand = (command: BboxCommand) => {
    const newAnnotations = command.execute(annotations)
    setAnnotations(newAnnotations)
    onAnnotationsChange(newAnnotations)

    // Add to undo stack and clear redo stack
    setUndoStack(prev => [...prev, command])
    setRedoStack([])
  }

  // Undo last command
  const undo = () => {
    if (undoStack.length === 0) return

    const command = undoStack[undoStack.length - 1]
    const newAnnotations = command.undo(annotations)
    setAnnotations(newAnnotations)
    onAnnotationsChange(newAnnotations)

    // Move command from undo to redo stack
    setUndoStack(prev => prev.slice(0, -1))
    setRedoStack(prev => [...prev, command])
  }

  // Redo last undone command
  const redo = () => {
    if (redoStack.length === 0) return

    const command = redoStack[redoStack.length - 1]
    const newAnnotations = command.execute(annotations)
    setAnnotations(newAnnotations)
    onAnnotationsChange(newAnnotations)

    // Move command from redo to undo stack
    setRedoStack(prev => prev.slice(0, -1))
    setUndoStack(prev => [...prev, command])
  }

  // Coordinate transforms live in src/utils/coordinates.ts — shared across
  // annotation components. Use screenToImage / scaleBbox / fitScale from there.

  // Load and scale image
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const img = new Image()
    img.onload = () => {
      // Use most of the window width (minimal padding)
      const availableWidth = window.innerWidth - 100
      const scale = fitScale(imageWidth, availableWidth)

      canvas.width = imageWidth * scale
      canvas.height = imageHeight * scale

      setScale(scale)
      setImageLoaded(true)

      // Draw image
      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
        redrawAnnotations(ctx, annotations)  // Draw initial annotations (including AI suggestions)
      }
    }
    img.src = imageUrl
  }, [imageUrl, imageWidth, imageHeight])

  // Redraw canvas
  useEffect(() => {
    if (!imageLoaded) return
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Clear and redraw image
    const img = new Image()
    img.onload = () => {
      // Clear and draw image
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

      // Draw annotations
      redrawAnnotations(ctx, annotations)

      // Draw current drawing box
      if (drawing.isDrawing) {
        const start = screenToImage(drawing.startX, drawing.startY, scale)
        const end = screenToImage(drawing.currentX, drawing.currentY, scale)

        drawBox(ctx, {
          x: Math.min(start.x, end.x) * scale,
          y: Math.min(start.y, end.y) * scale,
          width: Math.abs(end.x - start.x) * scale,
          height: Math.abs(end.y - start.y) * scale
        }, 'yellow', true)
      }
    }
    img.src = imageUrl
  }, [annotations, selectedId, highlightedId, drawing, imageLoaded, imageUrl])

  const redrawAnnotations = (ctx: CanvasRenderingContext2D, boxes: BboxAnnotation[]) => {
    boxes.forEach((box, index) => {
      const scaledBox = scaleBbox(box, scale)
      const isSelected = box.id === selectedId
      const isHighlighted = box.id === highlightedId

      // Color coding priority (highest wins):
      // - Cyan:         Highlighted from validation panel hover
      // - Bright green: User-selected (so selection is always visible)
      // - Purple:       AI prediction (pending — not yet validated)
      // - Green:        Accepted AI prediction (correct ✓) / validated
      // - Per-faction:  Default manual annotation — one stable hue per
      //                 `classLabel` so multi-faction scenes read at a
      //                 glance. Cached thumbs stay visually consistent
      //                 across images (space_marines always blue-ish etc).
      let color = factionStrokeColour(box.classLabel || 'manual')
      if (isHighlighted) {
        color = '#00ffff'  // Cyan for highlighted from panel
      } else if (isSelected) {
        color = '#00ff00'  // Bright green for selected — always win
      } else if (box.isAccepted) {
        color = '#22c55e'  // Green for accepted predictions
      } else if (box.isPrediction) {
        color = '#7c3aed'  // Purple for pending AI predictions
      } else if (box.validated) {
        color = '#10b981'  // Green for validated
      }

      // Draw bbox with thicker line for predictions
      drawBox(ctx, scaledBox, color, isSelected || box.isPrediction)

      // Build label text. When a unit_slug is set we render it alongside
      // the faction so at-a-glance you see both halves of the label
      // (e.g. "space_marines / intercessors"). Empty unit stays hidden.
      const factionText = box.classLabel.replace(/_/g, ' ')
      const unitText = box.unit_slug ? ` / ${box.unit_slug.replace(/_/g, ' ')}` : ''
      let labelText = ''
      if (box.isAccepted) {
        // Accepted prediction: show ✓ and class
        const confidence = box.confidence ? ` ${Math.round(box.confidence * 100)}%` : ''
        labelText = `✓ ${factionText}${unitText}${confidence}`
      } else if (box.isPrediction) {
        // Pending prediction: show number, class, and confidence
        const predIndex = boxes.filter(b => b.isPrediction).indexOf(box) + 1
        const confidence = box.confidence ? ` ${Math.round(box.confidence * 100)}%` : ''
        labelText = `#${predIndex} ${factionText}${unitText}${confidence}`
      } else {
        labelText = `${factionText}${unitText}`
      }

      // Draw label background for better visibility
      ctx.font = 'bold 14px Arial'
      const textMetrics = ctx.measureText(labelText)
      const textHeight = 16
      const padding = 4

      // Background rectangle
      ctx.fillStyle = color
      ctx.fillRect(
        scaledBox.x,
        scaledBox.y - textHeight - padding,
        textMetrics.width + padding * 2,
        textHeight + padding
      )

      // Label text in white
      ctx.fillStyle = '#ffffff'
      ctx.fillText(labelText, scaledBox.x + padding, scaledBox.y - padding - 2)

      // Draw resize handles for selected or hovered box
      if (isSelected || isHighlighted) {
        const hs = HANDLE_SIZE / 2
        const handlePositions = [
          { x: scaledBox.x, y: scaledBox.y },                                          // nw
          { x: scaledBox.x + scaledBox.width, y: scaledBox.y },                        // ne
          { x: scaledBox.x, y: scaledBox.y + scaledBox.height },                       // sw
          { x: scaledBox.x + scaledBox.width, y: scaledBox.y + scaledBox.height },     // se
          { x: scaledBox.x + scaledBox.width / 2, y: scaledBox.y },                    // n
          { x: scaledBox.x + scaledBox.width / 2, y: scaledBox.y + scaledBox.height }, // s
          { x: scaledBox.x, y: scaledBox.y + scaledBox.height / 2 },                   // w
          { x: scaledBox.x + scaledBox.width, y: scaledBox.y + scaledBox.height / 2 }, // e
        ]
        for (const hp of handlePositions) {
          ctx.fillStyle = '#ffffff'
          ctx.fillRect(hp.x - hs, hp.y - hs, HANDLE_SIZE, HANDLE_SIZE)
          ctx.strokeStyle = color
          ctx.lineWidth = 1
          ctx.strokeRect(hp.x - hs, hp.y - hs, HANDLE_SIZE, HANDLE_SIZE)
        }
      }
    })
  }

  const drawBox = (
    ctx: CanvasRenderingContext2D,
    box: { x: number, y: number, width: number, height: number },
    color: string,
    thick: boolean = false
  ) => {
    ctx.strokeStyle = color
    ctx.lineWidth = thick ? 3 : 2
    ctx.strokeRect(box.x, box.y, box.width, box.height)
  }

  const getMousePos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }

    const rect = canvas.getBoundingClientRect()
    // Account for CSS zoom transform
    return {
      x: (e.clientX - rect.left) / zoom,
      y: (e.clientY - rect.top) / zoom
    }
  }

  // Handle mouse wheel zoom
  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    // Only zoom if Ctrl is held (otherwise allow normal scroll)
    if (!e.ctrlKey) return

    e.preventDefault()

    const delta = e.deltaY > 0 ? -0.1 : 0.1
    setZoom(prev => Math.max(0.1, Math.min(10, prev + delta)))
  }

  // Zoom controls
  const zoomIn = () => setZoom(prev => Math.min(10, prev + 0.25))
  const zoomOut = () => setZoom(prev => Math.max(0.1, prev - 0.25))
  const resetZoom = () => setZoom(1)

  // Apply a resize delta to a box based on which handle is being dragged
  const applyResize = (
    orig: { x: number; y: number; width: number; height: number },
    handle: ResizeHandle,
    deltaX: number,
    deltaY: number,
  ) => {
    let { x, y, width, height } = orig
    const MIN_SIZE = 10

    switch (handle) {
      case 'se': width += deltaX; height += deltaY; break
      case 'nw': x += deltaX; y += deltaY; width -= deltaX; height -= deltaY; break
      case 'ne': y += deltaY; width += deltaX; height -= deltaY; break
      case 'sw': x += deltaX; width -= deltaX; height += deltaY; break
      case 'n': y += deltaY; height -= deltaY; break
      case 's': height += deltaY; break
      case 'w': x += deltaX; width -= deltaX; break
      case 'e': width += deltaX; break
    }

    // Enforce minimum size
    if (width < MIN_SIZE) { width = MIN_SIZE }
    if (height < MIN_SIZE) { height = MIN_SIZE }

    return { x, y, width, height }
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    // Only handle left mouse button
    if (e.button !== 0) return

    const screenPos = getMousePos(e)
    const imagePos = screenToImage(screenPos.x, screenPos.y, scale)

    // Check resize handles first (higher priority than box selection)
    const hit = getHandleAtPoint(screenPos.x, screenPos.y, annotations, scale)
    if (hit) {
      const box = annotations.find(a => a.id === hit.boxId)
      if (box) {
        setSelectedId(hit.boxId)
        onBoxSelected?.(hit.boxId)
        setResizing({
          isResizing: true,
          boxId: hit.boxId,
          handle: hit.handle,
          origX: box.x,
          origY: box.y,
          origWidth: box.width,
          origHeight: box.height,
        })
        return
      }
    }

    // Helper: check if point is inside a bbox (in image coordinates)
    const isPointInBox = (box: BboxAnnotation, point: { x: number, y: number }) => {
      return point.x >= box.x && point.x <= box.x + box.width &&
             point.y >= box.y && point.y <= box.y + box.height
    }

    // Check if clicking on any existing box (in image coordinates)
    // Collect all overlapping boxes, smallest-area first (most specific box wins)
    const overlapping = annotations
      .filter(box => isPointInBox(box, imagePos))
      .sort((a, b) => (a.width * a.height) - (b.width * b.height))

    if (overlapping.length > 0) {
      // Cycle: if the currently selected box is among the overlapping ones,
      // pick the next one in the list so repeated clicks rotate through them
      const currentIdx = overlapping.findIndex(b => b.id === selectedId)
      const next = currentIdx >= 0
        ? overlapping[(currentIdx + 1) % overlapping.length]
        : overlapping[0]
      setSelectedId(next.id)
      onBoxSelected?.(next.id)
      return
    }

    // Start drawing new box (deselect first)
    setSelectedId(null)
    onBoxSelected?.(null)  // Notify parent of deselection
    setDrawing({
      isDrawing: true,
      startX: screenPos.x,
      startY: screenPos.y,
      currentX: screenPos.x,
      currentY: screenPos.y
    })
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const screenPos = getMousePos(e)

    // Resizing in progress
    if (resizing.isResizing) {
      const imagePos = screenToImage(screenPos.x, screenPos.y, scale)
      const origin = screenToImage(0, 0, scale)
      const deltaX = imagePos.x - origin.x - resizing.origX
      const deltaY = imagePos.y - origin.y - resizing.origY

      // Compute absolute delta from original box position
      const newRect = applyResize(
        { x: resizing.origX, y: resizing.origY, width: resizing.origWidth, height: resizing.origHeight },
        resizing.handle,
        imagePos.x - (resizing.origX + (resizing.handle.includes('e') ? resizing.origWidth : resizing.handle.includes('w') ? 0 : resizing.origWidth / 2)),
        imagePos.y - (resizing.origY + (resizing.handle.includes('s') ? resizing.origHeight : resizing.handle.includes('n') ? 0 : resizing.origHeight / 2)),
      )

      setAnnotations(prev => prev.map(a =>
        a.id === resizing.boxId ? { ...a, ...newRect } : a
      ))
      return
    }

    // Drawing in progress
    if (drawing.isDrawing) {
      setDrawing(prev => ({
        ...prev,
        currentX: screenPos.x,
        currentY: screenPos.y
      }))
      return
    }

    // Hover: update cursor based on handle proximity
    const hit = getHandleAtPoint(screenPos.x, screenPos.y, annotations, scale)
    setHoverCursor(hit ? HANDLE_CURSORS[hit.handle] : 'default')
  }

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    // Finish resizing
    if (resizing.isResizing) {
      const box = annotations.find(a => a.id === resizing.boxId)
      if (box) {
        // Record as a command for undo support: delete old, add new
        const oldBox: BboxAnnotation = {
          ...box,
          x: resizing.origX,
          y: resizing.origY,
          width: resizing.origWidth,
          height: resizing.origHeight,
        }
        // Create a resize command (delete old + add new)
        const command = {
          execute(anns: BboxAnnotation[]) {
            return anns.map(a => a.id === box.id
              ? { ...a, x: box.x, y: box.y, width: box.width, height: box.height } : a)
          },
          undo(anns: BboxAnnotation[]) {
            return anns.map(a => a.id === box.id
              ? { ...a, x: oldBox.x, y: oldBox.y, width: oldBox.width, height: oldBox.height } : a)
          },
          description: 'Resize box'
        }
        // Push to undo stack (annotations are already updated via live preview)
        setUndoStack(prev => [...prev, command])
        setRedoStack([])
        onAnnotationsChange(annotations)
      }
      setResizing({ isResizing: false, boxId: '', handle: 'se', origX: 0, origY: 0, origWidth: 0, origHeight: 0 })
      return
    }

    if (!drawing.isDrawing) return

    const screenPos = getMousePos(e)
    const width = Math.abs(screenPos.x - drawing.startX)
    const height = Math.abs(screenPos.y - drawing.startY)

    // Minimum size check (10px in screen space)
    if (width < 10 || height < 10) {
      setDrawing({ isDrawing: false, startX: 0, startY: 0, currentX: 0, currentY: 0 })
      return
    }

    // Convert screen coordinates to image coordinates
    const startImage = screenToImage(drawing.startX, drawing.startY, scale)
    const endImage = screenToImage(screenPos.x, screenPos.y, scale)

    // Create new annotation (in image coordinates)
    const newAnnotation: BboxAnnotation = {
      id: crypto.randomUUID(),
      x: Math.min(startImage.x, endImage.x),
      y: Math.min(startImage.y, endImage.y),
      width: Math.abs(endImage.x - startImage.x),
      height: Math.abs(endImage.y - startImage.y),
      classLabel: currentClass,
      // Inherit the default unit if one's been picked (new bbox starts
      // pre-labelled). Omit when blank so the JSON stays clean.
      ...(currentUnit ? { unit_slug: currentUnit } : {}),
    }

    // Use command pattern for undo/redo
    const command = new AddModelBoxCommand(newAnnotation)
    executeCommand(command)

    setDrawing({ isDrawing: false, startX: 0, startY: 0, currentX: 0, currentY: 0 })
  }

  const handleDeleteSelected = () => {
    if (!selectedId) return

    const bbox = annotations.find(a => a.id === selectedId)
    if (!bbox) return

    // Use command pattern for undo/redo
    const command = new DeleteModelBoxCommand(bbox)
    executeCommand(command)
    setSelectedId(null)
  }

  const handleClassChange = (newClass: string) => {
    if (newClass !== currentClass) {
      setCurrentClass(newClass)
      // Clear the default unit when the default faction changes — the
      // old unit isn't valid under the new faction.
      setCurrentUnit('')
    }

    // Update selected box via command pattern for undo support.
    // If the box already had a unit_slug, clear it — a unit from faction A
    // isn't meaningful under faction B. The user picks the new unit from
    // the unit dropdown if desired. Two separate commands keeps undo
    // granular: you can undo the faction change and get the unit back.
    if (selectedId) {
      const box = annotations.find(a => a.id === selectedId)
      if (box && box.classLabel !== newClass) {
        const factionCmd = new ChangeClassCommand(selectedId, box.classLabel, newClass)
        executeCommand(factionCmd)
        if (box.unit_slug) {
          const unitCmd = new ChangeUnitCommand(selectedId, box.unit_slug, undefined)
          executeCommand(unitCmd)
        }
      }
    }
  }

  /** Change the unit_slug of the currently-selected bbox, OR — when
   *  no bbox is selected — set the default unit for the next bbox you
   *  draw (mirrors how the faction picker writes to `currentClass`).
   *  Empty string means "clear" (the deferred-labelling pattern). */
  const handleUnitChange = (newUnit: string) => {
    if (!selectedId) {
      // No bbox selected → write the default for new draws.
      setCurrentUnit(newUnit)
      return
    }
    const box = annotations.find(a => a.id === selectedId)
    if (!box) return
    const normalised = newUnit || undefined
    if (box.unit_slug === normalised) return
    const cmd = new ChangeUnitCommand(selectedId, box.unit_slug, normalised)
    executeCommand(cmd)
  }

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't interfere if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) {
        return
      }

      // Undo/Redo (Ctrl+Z / Ctrl+Shift+Z)
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        if (e.shiftKey) {
          redo()
        } else {
          undo()
        }
        return
      }

      // Redo alternative (Ctrl+Y)
      if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
        e.preventDefault()
        redo()
        return
      }

      // Save (Ctrl+S or S)
      if (e.key === 's' || e.key === 'S') {
        e.preventDefault()
        onSaveRequested?.()
        return
      }

      // Skip (K key)
      if (e.key === 'k' || e.key === 'K') {
        e.preventDefault()
        onSkipRequested?.()
        return
      }

      // Flag as unusable (X key)
      if (e.key === 'x' || e.key === 'X') {
        e.preventDefault()
        onFlagRequested?.()
        return
      }

      // Back to previous image (B key)
      if (e.key === 'b' || e.key === 'B') {
        e.preventDefault()
        onBackRequested?.()
        return
      }

      // Zoom controls
      if (e.key === '+' || e.key === '=') {
        e.preventDefault()
        zoomIn()
        return
      }
      if (e.key === '-') {
        e.preventDefault()
        zoomOut()
        return
      }
      if (e.key === '0') {
        e.preventDefault()
        resetZoom()
        return
      }

      // Delete selected box
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault()
        handleDeleteSelected()
        return
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedId, annotations, undoStack, redoStack, onSaveRequested, onSkipRequested, onFlagRequested, onBackRequested, zoom])

  // Handle mouseup outside canvas — cancel stuck drawing/resizing
  useEffect(() => {
    if (!drawing.isDrawing && !resizing.isResizing) return

    const handleWindowMouseUp = (e: MouseEvent) => {
      if (canvasRef.current?.contains(e.target as Node)) return

      if (drawing.isDrawing) {
        setDrawing({ isDrawing: false, startX: 0, startY: 0, currentX: 0, currentY: 0 })
      }
      if (resizing.isResizing) {
        setAnnotations(prev => prev.map(a =>
          a.id === resizing.boxId
            ? { ...a, x: resizing.origX, y: resizing.origY, width: resizing.origWidth, height: resizing.origHeight }
            : a
        ))
        setResizing({ isResizing: false, boxId: '', handle: 'se', origX: 0, origY: 0, origWidth: 0, origHeight: 0 })
      }
    }

    window.addEventListener('mouseup', handleWindowMouseUp)
    return () => window.removeEventListener('mouseup', handleWindowMouseUp)
  }, [drawing.isDrawing, resizing.isResizing, resizing.boxId, resizing.origX, resizing.origY, resizing.origWidth, resizing.origHeight])

  return (
    <div className="bbox-annotator">
      {/* Controls */}
      <div className="annotation-controls" style={{
        marginBottom: '1rem',
        padding: '1rem',
        backgroundColor: '#1a1a1a',
        borderRadius: '8px',
        border: '1px solid #333'
      }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Faction (class) + unit pickers. When a bbox is selected we
              show and edit THAT bbox's faction + unit — so you can label
              different minis in a multi-faction scene independently.
              When nothing is selected the dropdowns set the default
              class/unit for the next bbox you draw.
              `unitsByFaction` is optional: if the taxonomy endpoint
              hasn't loaded yet, the unit picker simply doesn't render. */}
          {(() => {
            const selectedBox = selectedId
              ? annotations.find(a => a.id === selectedId) ?? null
              : null
            const effectiveFaction = selectedBox?.classLabel ?? currentClass
            // Bbox selected → that bbox's unit. Nothing selected → the
            // default that pre-populates new draws.
            const effectiveUnit = selectedBox ? (selectedBox.unit_slug ?? '') : currentUnit
            const factionUnits = unitsByFaction?.[effectiveFaction] ?? []
            return (
              <>
                <div>
                  <label style={{ marginRight: '0.5rem', color: '#aaa' }}>Faction:</label>
                  <select
                    value={effectiveFaction}
                    onChange={(e) => handleClassChange(e.target.value)}
                    style={{
                      padding: '0.5rem',
                      backgroundColor: '#2a2a2a',
                      color: '#fff',
                      border: '1px solid #444',
                      borderRadius: '4px',
                      minWidth: '180px',
                    }}
                  >
                    {classLabels.map(label => (
                      <option key={label} value={label}>{label}</option>
                    ))}
                  </select>
                </div>
                {unitsByFaction && (() => {
                  // Native <select>. Previously a <datalist>-backed
                  // typeahead, but datalist is unreliable in practice —
                  // Chromium sometimes refuses to pop the suggestion
                  // list for larger option sets, which made the 329
                  // space_marines units effectively invisible. A plain
                  // select is universally supported, scrollable, and
                  // the browser's native first-letter-jump ("in" →
                  // first "In…" option) covers the search use case.
                  //
                  // units.json has a few duplicate entries per faction
                  // (same slug appearing twice with different
                  // categories). Dedupe by slug so React keys are
                  // unique and the dropdown isn't cluttered.
                  const dedupedUnits = Array.from(
                    new Map(factionUnits.map(u => [u.slug, u])).values()
                  )
                  return (
                    <div>
                      <label style={{ marginRight: '0.5rem', color: '#aaa' }}>
                        Unit <span style={{ color: '#666', fontSize: '0.85rem' }}>(optional)</span>:
                      </label>
                      <select
                        value={effectiveUnit}
                        onChange={(e) => handleUnitChange(e.target.value)}
                        title={selectedBox
                          ? `Pick a unit for the selected bbox (${dedupedUnits.length} ${effectiveFaction} units). Type first letters to jump.`
                          : `Set the default unit for the NEXT bbox you draw. Click an existing bbox to set ITS unit instead.`}
                        style={{
                          padding: '0.5rem',
                          backgroundColor: '#2a2a2a',
                          color: '#fff',
                          border: '1px solid #444',
                          borderRadius: '4px',
                          minWidth: '260px',
                          maxWidth: '360px',
                        }}
                      >
                        <option value="">— defer / none —</option>
                        {dedupedUnits.map(u => (
                          <option key={u.slug} value={u.slug}>
                            {u.name}{u.category ? ` · ${u.category}` : ''}
                          </option>
                        ))}
                      </select>
                      {!selectedBox && currentUnit && (
                        <span style={{
                          marginLeft: '0.5rem',
                          fontSize: '0.75rem',
                          color: '#a855f7',
                        }} title="New bboxes you draw will start with this unit pre-selected">
                          applies to next draw
                        </span>
                      )}
                    </div>
                  )
                })()}
              </>
            )
          })()}

          {/* Zoom controls */}
          <div style={{ display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
            <button
              onClick={zoomOut}
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: '#2a2a2a',
                color: '#fff',
                border: '1px solid #444',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '0.85rem'
              }}
              title="Zoom out (-)"
            >
              −
            </button>
            <span style={{ color: '#aaa', fontSize: '0.85rem', minWidth: '50px', textAlign: 'center' }}>
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={zoomIn}
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: '#2a2a2a',
                color: '#fff',
                border: '1px solid #444',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '0.85rem'
              }}
              title="Zoom in (+)"
            >
              +
            </button>
            <button
              onClick={resetZoom}
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: '#2a2a2a',
                color: '#fff',
                border: '1px solid #444',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '0.85rem',
                marginLeft: '0.25rem'
              }}
              title="Reset zoom (0)"
            >
              Fit
            </button>
          </div>

          {/* Undo/Redo controls */}
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginLeft: 'auto' }}>
            <button
              onClick={undo}
              disabled={undoStack.length === 0}
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: undoStack.length > 0 ? '#2a2a2a' : '#1a1a1a',
                color: undoStack.length > 0 ? '#fff' : '#666',
                border: '1px solid #444',
                borderRadius: '4px',
                cursor: undoStack.length > 0 ? 'pointer' : 'not-allowed',
                fontSize: '0.85rem',
                opacity: undoStack.length > 0 ? 1 : 0.5
              }}
              title="Undo (Ctrl+Z)"
            >
              ↶ Undo
            </button>
            <button
              onClick={redo}
              disabled={redoStack.length === 0}
              style={{
                padding: '0.5rem 0.75rem',
                backgroundColor: redoStack.length > 0 ? '#2a2a2a' : '#1a1a1a',
                color: redoStack.length > 0 ? '#fff' : '#666',
                border: '1px solid #444',
                borderRadius: '4px',
                cursor: redoStack.length > 0 ? 'pointer' : 'not-allowed',
                fontSize: '0.85rem',
                opacity: redoStack.length > 0 ? 1 : 0.5
              }}
              title="Redo (Ctrl+Shift+Z or Ctrl+Y)"
            >
              ↷ Redo
            </button>
          </div>

          {/* Stats */}
          <div style={{ color: '#aaa', fontSize: '0.9rem' }}>
            Boxes: <span style={{ color: '#00ff00', fontWeight: 'bold' }}>{annotations.length}</span>
          </div>

          {/* Delete button */}
          {selectedId && (
            <button
              onClick={handleDeleteSelected}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: '#dc2626',
                color: '#fff',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              Delete (Del)
            </button>
          )}
        </div>

        {/* Instructions */}
        <div style={{ marginTop: '0.75rem', color: '#666', fontSize: '0.85rem' }}>
          💡 Click and drag to draw boxes • Click to select • Del to remove • S to save • K to skip • +/- to zoom • Ctrl+scroll to zoom
        </div>
      </div>

      {/* Canvas and Legend Container */}
      <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
        {/* Canvas with scrollable zoom container */}
        <div ref={containerRef} style={{ flex: 1, minWidth: 0 }}>
          <div
            onWheel={handleWheel}
            style={{
              maxHeight: '90vh',
              overflow: 'auto',
              border: '2px solid #444',
              borderRadius: '8px',
              backgroundColor: '#111'
            }}
          >
            <canvas
              ref={canvasRef}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              style={{
                display: 'block',
                cursor: drawing.isDrawing ? 'crosshair' : resizing.isResizing ? HANDLE_CURSORS[resizing.handle] : hoverCursor,
                userSelect: 'none',
                transform: `scale(${zoom})`,
                transformOrigin: 'top left'
              }}
            />
          </div>
        </div>

      </div>
    </div>
  )
}
