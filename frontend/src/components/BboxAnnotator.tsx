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

interface BboxAnnotatorProps {
  imageUrl: string
  imageWidth: number
  imageHeight: number
  onAnnotationsChange: (annotations: BboxAnnotation[]) => void
  classLabels: string[]  // Available class labels
  defaultClass?: string
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

// ═══════════════════════════════════════════════════════════
// COMMAND PATTERN FOR UNDO/REDO
// ═══════════════════════════════════════════════════════════

interface Command {
  execute(annotations: BboxAnnotation[]): BboxAnnotation[]
  undo(annotations: BboxAnnotation[]): BboxAnnotation[]
  description: string
}

class AddModelBoxCommand implements Command {
  constructor(private bbox: BboxAnnotation) {}

  execute(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return [...annotations, this.bbox]
  }

  undo(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return annotations.filter(a => a.id !== this.bbox.id)
  }

  description = 'Add model box'
}

class DeleteModelBoxCommand implements Command {
  constructor(private bbox: BboxAnnotation) {}

  execute(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return annotations.filter(a => a.id !== this.bbox.id)
  }

  undo(annotations: BboxAnnotation[]): BboxAnnotation[] {
    return [...annotations, this.bbox]
  }

  description = 'Delete model box'
}

export default function BboxAnnotator({
  imageUrl,
  imageWidth,
  imageHeight,
  onAnnotationsChange,
  classLabels,
  defaultClass = 'miniature',
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
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  const [annotations, setAnnotations] = useState<BboxAnnotation[]>(initialAnnotations)
  const [selectedId, setSelectedId] = useState<string | null>(null)

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
  const [imageLoaded, setImageLoaded] = useState(false)

  // Undo/Redo stacks
  const [undoStack, setUndoStack] = useState<Command[]>([])
  const [redoStack, setRedoStack] = useState<Command[]>([])

  // Execute a command and add to undo stack
  const executeCommand = (command: Command) => {
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

  // ═══════════════════════════════════════════════════════════
  // COORDINATE TRANSFORMS
  // ═══════════════════════════════════════════════════════════

  /**
   * Convert screen coordinates (canvas pixels) → image coordinates (actual image pixels)
   */
  const screenToImage = (screenX: number, screenY: number) => {
    return {
      x: screenX / scale,
      y: screenY / scale
    }
  }

  // Load and scale image
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const img = new Image()
    img.onload = () => {
      // Use most of the window width (minimal padding)
      const availableWidth = window.innerWidth - 100
      const scale = availableWidth / imageWidth

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
        const start = screenToImage(drawing.startX, drawing.startY)
        const end = screenToImage(drawing.currentX, drawing.currentY)

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
      const scaledBox = {
        x: box.x * scale,
        y: box.y * scale,
        width: box.width * scale,
        height: box.height * scale
      }
      const isSelected = box.id === selectedId
      const isHighlighted = box.id === highlightedId

      // Color coding:
      // - Cyan:   Highlighted from validation panel hover
      // - Purple: AI prediction (pending — not yet validated)
      // - Green:  Accepted AI prediction (correct ✓)
      // - Red:    Manual annotation
      let color = '#ff0000'  // Default red for manual
      if (isHighlighted) {
        color = '#00ffff'  // Cyan for highlighted from panel
      } else if (box.isAccepted) {
        color = '#22c55e'  // Green for accepted predictions
      } else if (box.isPrediction) {
        color = isSelected ? '#a855f7' : '#7c3aed'  // Purple for pending AI predictions
      } else if (box.validated) {
        color = '#10b981'  // Green for validated
      } else if (isSelected) {
        color = '#00ff00'  // Bright green for selected
      }

      // Draw bbox with thicker line for predictions
      drawBox(ctx, scaledBox, color, isSelected || box.isPrediction)

      // Build label text
      let labelText = ''
      if (box.isAccepted) {
        // Accepted prediction: show ✓ and class
        const confidence = box.confidence ? ` ${Math.round(box.confidence * 100)}%` : ''
        labelText = `✓ ${box.classLabel.replace(/_/g, ' ')}${confidence}`
      } else if (box.isPrediction) {
        // Pending prediction: show number, class, and confidence
        const predIndex = boxes.filter(b => b.isPrediction).indexOf(box) + 1
        const confidence = box.confidence ? ` ${Math.round(box.confidence * 100)}%` : ''
        labelText = `#${predIndex} ${box.classLabel.replace(/_/g, ' ')}${confidence}`
      } else {
        labelText = box.classLabel.replace(/_/g, ' ')
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

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    // Only handle left mouse button
    if (e.button !== 0) return

    const screenPos = getMousePos(e)
    const imagePos = screenToImage(screenPos.x, screenPos.y)

    // Helper: check if point is inside a bbox (in image coordinates)
    const isPointInBox = (box: BboxAnnotation, point: { x: number, y: number }) => {
      return point.x >= box.x && point.x <= box.x + box.width &&
             point.y >= box.y && point.y <= box.y + box.height
    }

    // Check if clicking on any existing box (in image coordinates)
    const clickedBox = annotations.find(box => isPointInBox(box, imagePos))

    // Clicking a box selects it
    if (clickedBox) {
      setSelectedId(clickedBox.id)
      onBoxSelected?.(clickedBox.id)  // Notify parent of selection
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
    if (!drawing.isDrawing) return

    const screenPos = getMousePos(e)
    setDrawing(prev => ({
      ...prev,
      currentX: screenPos.x,
      currentY: screenPos.y
    }))
  }

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
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
    const startImage = screenToImage(drawing.startX, drawing.startY)
    const endImage = screenToImage(screenPos.x, screenPos.y)

    // Create new annotation (in image coordinates)
    const newAnnotation: BboxAnnotation = {
      id: crypto.randomUUID(),
      x: Math.min(startImage.x, endImage.x),
      y: Math.min(startImage.y, endImage.y),
      width: Math.abs(endImage.x - startImage.x),
      height: Math.abs(endImage.y - startImage.y),
      classLabel: currentClass
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
    setCurrentClass(newClass)

    // Also update selected box if any
    if (selectedId) {
      const updatedAnnotations = annotations.map(a =>
        a.id === selectedId ? { ...a, classLabel: newClass } : a
      )
      setAnnotations(updatedAnnotations)
      onAnnotationsChange(updatedAnnotations)
    }
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
        if (e.ctrlKey || e.metaKey || !e.ctrlKey) {  // Allow both Ctrl+S and just S
          e.preventDefault()
          onSaveRequested?.()
        }
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
          {/* Class selector */}
          <div>
            <label style={{ marginRight: '0.5rem', color: '#aaa' }}>Class:</label>
            <select
              value={currentClass}
              onChange={(e) => handleClassChange(e.target.value)}
              style={{
                padding: '0.5rem',
                backgroundColor: '#2a2a2a',
                color: '#fff',
                border: '1px solid #444',
                borderRadius: '4px'
              }}
            >
              {classLabels.map(label => (
                <option key={label} value={label}>{label}</option>
              ))}
            </select>
          </div>

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
            ref={scrollContainerRef}
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
                cursor: drawing.isDrawing ? 'crosshair' : 'default',
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
