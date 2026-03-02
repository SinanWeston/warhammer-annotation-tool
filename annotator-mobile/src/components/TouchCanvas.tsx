import { useRef, useEffect, useCallback } from 'react'
import type { MobileBbox, PredictionBox } from '../types'

interface Point { x: number; y: number }
interface Rect { x: number; y: number; width: number; height: number }

interface Props {
  imageBlob: Blob
  imageWidth: number
  imageHeight: number
  bboxes: MobileBbox[]
  predictions: PredictionBox[]
  acceptedPredictionIds: Set<string>
  rejectedPredictionIds: Set<string>
  highlightPredictionIndex: number | null
  pendingBbox: Rect | null
  onDrawComplete: (rect: Rect) => void
}

export default function TouchCanvas({
  imageBlob,
  imageWidth,
  imageHeight,
  bboxes,
  predictions,
  acceptedPredictionIds,
  rejectedPredictionIds,
  highlightPredictionIndex,
  pendingBbox,
  onDrawComplete,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const imageUrlRef = useRef<string | null>(null)

  // Drawing state (refs — no re-renders during drag)
  const drawStartRef = useRef<Point | null>(null)
  const drawCurrentRef = useRef<Point | null>(null)
  const isDraggingRef = useRef(false)

  // Zoom/pan
  const gestureRef = useRef<'none' | 'draw' | 'pinch-pan'>('none')
  const zoomRef = useRef(1)
  const panRef = useRef<Point>({ x: 0, y: 0 })
  const pinchStartRef = useRef<{ dist: number; zoom: number; mid: Point; pan: Point } | null>(null)

  const canvasSizedRef = useRef(false)
  const rafRef = useRef(0)
  const imageOffsetRef = useRef<Point>({ x: 0, y: 0 })

  // Keep props in refs for use inside draw/handlers
  const pendingBboxRef = useRef<Rect | null>(null)
  pendingBboxRef.current = pendingBbox

  const propsRef = useRef({ bboxes, predictions, acceptedPredictionIds, rejectedPredictionIds, highlightPredictionIndex })
  propsRef.current = { bboxes, predictions, acceptedPredictionIds, rejectedPredictionIds, highlightPredictionIndex }

  const onDrawCompleteRef = useRef(onDrawComplete)
  onDrawCompleteRef.current = onDrawComplete

  // ---- Coordinate helpers ----

  const getBaseScale = useCallback(() => {
    const container = containerRef.current
    if (!container || !imageWidth || !imageHeight) return 1
    return Math.min(container.clientWidth / imageWidth, container.clientHeight / imageHeight)
  }, [imageWidth, imageHeight])

  const screenToImage = useCallback((clientX: number, clientY: number): Point => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const baseScale = getBaseScale()
    const scale = baseScale * zoomRef.current
    return {
      x: (clientX - rect.left - imageOffsetRef.current.x - panRef.current.x) / scale,
      y: (clientY - rect.top - imageOffsetRef.current.y - panRef.current.y) / scale,
    }
  }, [getBaseScale])

  const clamp = useCallback((pt: Point): Point => ({
    x: Math.max(0, Math.min(imageWidth, pt.x)),
    y: Math.max(0, Math.min(imageHeight, pt.y)),
  }), [imageWidth, imageHeight])

  // ---- Canvas sizing ----

  const sizeCanvas = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container || !imageWidth || !imageHeight) return

    const dpr = window.devicePixelRatio || 1
    const cw = container.clientWidth
    const ch = container.clientHeight

    const targetW = Math.round(cw * dpr)
    const targetH = Math.round(ch * dpr)
    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW
      canvas.height = targetH
      canvas.style.width = `${cw}px`
      canvas.style.height = `${ch}px`
    }

    // Compute centering offset so image is centered within the full container
    const baseScale = Math.min(cw / imageWidth, ch / imageHeight)
    imageOffsetRef.current = {
      x: (cw - imageWidth * baseScale) / 2,
      y: (ch - imageHeight * baseScale) / 2,
    }

    canvasSizedRef.current = true
  }, [imageWidth, imageHeight])

  // ---- Draw ----

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    const img = imageRef.current
    const container = containerRef.current
    if (!canvas || !ctx || !img || !container) return

    if (!canvasSizedRef.current) sizeCanvas()

    const dpr = window.devicePixelRatio || 1
    const cw = container.clientWidth
    const ch = container.clientHeight
    const baseScale = Math.min(cw / imageWidth, ch / imageHeight)
    const zoom = zoomRef.current
    const pan = panRef.current
    const effectiveScale = baseScale * zoom

    const { bboxes: boxes, predictions: preds, acceptedPredictionIds: accIds, rejectedPredictionIds: rejIds, highlightPredictionIndex: hlIdx } = propsRef.current

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, cw, ch)

    ctx.save()
    ctx.translate(imageOffsetRef.current.x + pan.x, imageOffsetRef.current.y + pan.y)
    ctx.scale(effectiveScale, effectiveScale)

    // Image
    ctx.drawImage(img, 0, 0, imageWidth, imageHeight)

    // AI predictions (purple dashed)
    preds.forEach((pred, i) => {
      const predId = `pred-${i}`
      if (accIds.has(predId) || rejIds.has(predId)) return
      const isHl = hlIdx === i
      ctx.save()
      ctx.strokeStyle = isHl ? '#e879f9' : '#a855f7'
      ctx.lineWidth = (isHl ? 3 : 2) / effectiveScale
      ctx.setLineDash([6 / effectiveScale, 4 / effectiveScale])
      ctx.strokeRect(pred.x, pred.y, pred.width, pred.height)
      ctx.setLineDash([])
      const fs = Math.max(12, 14 / effectiveScale)
      ctx.font = `${fs}px Orbitron, monospace`
      const label = `${pred.classLabel} ${(pred.confidence * 100).toFixed(0)}%`
      const tw = ctx.measureText(label).width
      ctx.fillStyle = 'rgba(168, 85, 247, 0.7)'
      ctx.fillRect(pred.x, pred.y - fs - 4, tw + 8, fs + 4)
      ctx.fillStyle = '#fff'
      ctx.fillText(label, pred.x + 4, pred.y - 4)
      ctx.restore()
    })

    // Committed user bboxes (green solid)
    for (const bbox of boxes) {
      ctx.save()
      ctx.strokeStyle = '#4ade80'
      ctx.lineWidth = 2 / effectiveScale
      ctx.strokeRect(bbox.x, bbox.y, bbox.width, bbox.height)
      const fs = Math.max(12, 14 / effectiveScale)
      ctx.font = `bold ${fs}px Orbitron, monospace`
      const tw = ctx.measureText(bbox.classLabel).width
      ctx.fillStyle = 'rgba(74, 222, 128, 0.7)'
      ctx.fillRect(bbox.x, bbox.y - fs - 4, tw + 8, fs + 4)
      ctx.fillStyle = '#fff'
      ctx.fillText(bbox.classLabel, bbox.x + 4, bbox.y - 4)
      ctx.restore()
    }

    // Active drag preview (yellow dashed — finger is down)
    const drawStart = drawStartRef.current
    const drawCurrent = drawCurrentRef.current
    if (drawStart && drawCurrent && isDraggingRef.current) {
      drawPreviewRect(ctx, rectFromPoints(drawStart, drawCurrent), effectiveScale)
    }

    // Pending bbox (yellow dashed — waiting for confirm)
    const pending = pendingBboxRef.current
    if (pending && !isDraggingRef.current) {
      drawPreviewRect(ctx, pending, effectiveScale)
    }

    ctx.restore()

    // Zoom indicator
    if (zoom > 1.05) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const label = `${zoom.toFixed(1)}x`
      ctx.font = '11px Orbitron, monospace'
      const tw = ctx.measureText(label).width
      ctx.fillStyle = 'rgba(0,0,0,0.6)'
      ctx.fillRect(cw - tw - 16, 8, tw + 12, 20)
      ctx.fillStyle = '#fff'
      ctx.fillText(label, cw - tw - 10, 22)
    }
  }, [imageWidth, imageHeight, sizeCanvas])

  const scheduleRedraw = useCallback(() => {
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(() => draw())
  }, [draw])

  // ---- Image loading (only depends on imageBlob) ----

  const sizeCanvasRef = useRef(sizeCanvas)
  sizeCanvasRef.current = sizeCanvas
  const drawRef = useRef(draw)
  drawRef.current = draw

  useEffect(() => {
    const url = URL.createObjectURL(imageBlob)
    imageUrlRef.current = url
    const img = new Image()
    img.onload = () => {
      imageRef.current = img
      canvasSizedRef.current = false
      sizeCanvasRef.current()
      drawRef.current()
    }
    img.src = url
    return () => { URL.revokeObjectURL(url) }
  }, [imageBlob])

  // Reset on new image
  useEffect(() => {
    zoomRef.current = 1
    panRef.current = { x: 0, y: 0 }
    drawStartRef.current = null
    drawCurrentRef.current = null
    isDraggingRef.current = false
    gestureRef.current = 'none'
  }, [imageBlob])

  // Redraw on prop changes
  useEffect(() => { scheduleRedraw() }, [bboxes, predictions, acceptedPredictionIds, rejectedPredictionIds, highlightPredictionIndex, pendingBbox, scheduleRedraw])

  // Resize observer
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const ro = new ResizeObserver(() => {
      canvasSizedRef.current = false
      sizeCanvas()
      draw()
    })
    ro.observe(container)
    return () => ro.disconnect()
  }, [sizeCanvas, draw])

  // ---- Touch events ----

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const touchDist = (t1: Touch, t2: Touch) => {
      const dx = t2.clientX - t1.clientX
      const dy = t2.clientY - t1.clientY
      return Math.sqrt(dx * dx + dy * dy)
    }

    const touchMid = (t1: Touch, t2: Touch): Point => ({
      x: (t1.clientX + t2.clientX) / 2,
      y: (t1.clientY + t2.clientY) / 2,
    })

    const onTouchStart = (e: TouchEvent) => {
      e.preventDefault()

      if (e.touches.length === 2) {
        gestureRef.current = 'pinch-pan'
        drawStartRef.current = null
        drawCurrentRef.current = null
        isDraggingRef.current = false
        const t0 = e.touches[0], t1 = e.touches[1]
        pinchStartRef.current = {
          dist: touchDist(t0, t1),
          zoom: zoomRef.current,
          mid: touchMid(t0, t1),
          pan: { ...panRef.current },
        }
        scheduleRedraw()
        return
      }

      if (e.touches.length === 1) {
        gestureRef.current = 'draw'
        isDraggingRef.current = true
        const touch = e.touches[0]
        const pt = clamp(screenToImage(touch.clientX, touch.clientY))
        drawStartRef.current = pt
        drawCurrentRef.current = pt
        scheduleRedraw()
      }
    }

    const onTouchMove = (e: TouchEvent) => {
      e.preventDefault()

      if (gestureRef.current === 'pinch-pan' && e.touches.length === 2 && pinchStartRef.current) {
        const t0 = e.touches[0], t1 = e.touches[1]
        const newDist = touchDist(t0, t1)
        const newMid = touchMid(t0, t1)
        const scale = newDist / pinchStartRef.current.dist
        zoomRef.current = Math.max(1, Math.min(5, pinchStartRef.current.zoom * scale))
        panRef.current = {
          x: pinchStartRef.current.pan.x + (newMid.x - pinchStartRef.current.mid.x),
          y: pinchStartRef.current.pan.y + (newMid.y - pinchStartRef.current.mid.y),
        }
        scheduleRedraw()
        return
      }

      if (gestureRef.current === 'draw' && e.touches.length === 1 && drawStartRef.current) {
        const touch = e.touches[0]
        drawCurrentRef.current = clamp(screenToImage(touch.clientX, touch.clientY))
        scheduleRedraw()
      }
    }

    const onTouchEnd = (e: TouchEvent) => {
      e.preventDefault()

      if (gestureRef.current === 'pinch-pan') {
        if (e.touches.length === 0) {
          gestureRef.current = 'none'
          pinchStartRef.current = null
        }
        return
      }

      if (gestureRef.current === 'draw' && drawStartRef.current && drawCurrentRef.current) {
        isDraggingRef.current = false
        const r = rectFromPoints(drawStartRef.current, drawCurrentRef.current)
        drawStartRef.current = null
        drawCurrentRef.current = null
        gestureRef.current = 'none'

        if (r.width >= 5 && r.height >= 5) {
          onDrawCompleteRef.current(r)
        }
        scheduleRedraw()
      }
    }

    canvas.addEventListener('touchstart', onTouchStart, { passive: false })
    canvas.addEventListener('touchmove', onTouchMove, { passive: false })
    canvas.addEventListener('touchend', onTouchEnd, { passive: false })
    canvas.addEventListener('touchcancel', onTouchEnd, { passive: false })

    return () => {
      canvas.removeEventListener('touchstart', onTouchStart)
      canvas.removeEventListener('touchmove', onTouchMove)
      canvas.removeEventListener('touchend', onTouchEnd)
      canvas.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [screenToImage, clamp, scheduleRedraw])

  // ---- Mouse events (desktop) ----

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let mouseDown = false

    const onMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return
      mouseDown = true
      isDraggingRef.current = true
      const pt = clamp(screenToImage(e.clientX, e.clientY))
      drawStartRef.current = pt
      drawCurrentRef.current = pt
      scheduleRedraw()
    }

    const onMouseMove = (e: MouseEvent) => {
      if (!mouseDown || !drawStartRef.current) return
      drawCurrentRef.current = clamp(screenToImage(e.clientX, e.clientY))
      scheduleRedraw()
    }

    const onMouseUp = () => {
      if (!mouseDown) return
      mouseDown = false
      isDraggingRef.current = false

      if (drawStartRef.current && drawCurrentRef.current) {
        const r = rectFromPoints(drawStartRef.current, drawCurrentRef.current)
        drawStartRef.current = null
        drawCurrentRef.current = null
        if (r.width >= 5 && r.height >= 5) {
          onDrawCompleteRef.current(r)
        }
      }
      scheduleRedraw()
    }

    canvas.addEventListener('mousedown', onMouseDown)
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)

    return () => {
      canvas.removeEventListener('mousedown', onMouseDown)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [screenToImage, clamp, scheduleRedraw])

  return (
    <div ref={containerRef} className="relative flex-1 overflow-hidden bg-black">
      <canvas
        ref={canvasRef}
        className="block"
        style={{ touchAction: 'none' }}
      />
    </div>
  )
}

// ---- Pure helpers ----

function rectFromPoints(a: Point, b: Point): Rect {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    width: Math.abs(b.x - a.x),
    height: Math.abs(b.y - a.y),
  }
}

function drawPreviewRect(ctx: CanvasRenderingContext2D, r: Rect, effectiveScale: number) {
  ctx.save()
  ctx.fillStyle = 'rgba(250, 204, 21, 0.15)'
  ctx.fillRect(r.x, r.y, r.width, r.height)
  ctx.setLineDash([6 / effectiveScale, 4 / effectiveScale])
  ctx.strokeStyle = '#facc15'
  ctx.lineWidth = 3 / effectiveScale
  ctx.strokeRect(r.x, r.y, r.width, r.height)
  ctx.setLineDash([])
  ctx.restore()
}
