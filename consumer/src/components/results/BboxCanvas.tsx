import { useRef, useEffect, useCallback } from 'react'
import type { Detection } from '../../types/detection'
import { getFactionColor } from '../../utils/factions'

interface BboxCanvasProps {
  imageDataUrl: string
  imageWidth: number
  imageHeight: number
  detections: Detection[]
  highlightedId: string | null
  selectedId: string | null
  onHover: (canvasX: number, canvasY: number, detections: Detection[], scale: number) => void
  onClick: (canvasX: number, canvasY: number, detections: Detection[], scale: number) => void
}

export default function BboxCanvas({
  imageDataUrl, imageWidth, imageHeight, detections,
  highlightedId, selectedId, onHover, onClick
}: BboxCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const scaleRef = useRef(1)

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const img = imageRef.current
    if (!canvas || !img) return

    const container = containerRef.current
    if (!container) return

    const containerWidth = container.clientWidth
    const scale = containerWidth / imageWidth
    scaleRef.current = scale

    canvas.width = containerWidth
    canvas.height = imageHeight * scale

    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

    for (const det of detections) {
      const color = getFactionColor(det.faction)
      const isHighlighted = det.id === highlightedId
      const isSelected = det.id === selectedId

      const x = det.bbox.x * scale
      const y = det.bbox.y * scale
      const w = det.bbox.width * scale
      const h = det.bbox.height * scale

      // Fill
      ctx.fillStyle = `${color}${isHighlighted || isSelected ? '30' : '15'}`
      ctx.fillRect(x, y, w, h)

      // Stroke
      ctx.strokeStyle = color
      ctx.lineWidth = isSelected ? 3 : isHighlighted ? 2 : 1
      ctx.strokeRect(x, y, w, h)

      // Label
      const label = `${det.unitName} ${Math.round(det.confidence * 100)}%`
      ctx.font = '11px Orbitron, monospace'
      const textWidth = ctx.measureText(label).width
      const labelHeight = 16
      const labelY = y > labelHeight + 2 ? y - labelHeight - 2 : y

      ctx.fillStyle = `${color}cc`
      ctx.fillRect(x, labelY, textWidth + 8, labelHeight)
      ctx.fillStyle = '#fff'
      ctx.fillText(label, x + 4, labelY + 12)
    }
  }, [detections, highlightedId, selectedId, imageWidth, imageHeight])

  // Load image
  useEffect(() => {
    const img = new Image()
    img.onload = () => {
      imageRef.current = img
      draw()
    }
    img.src = imageDataUrl
  }, [imageDataUrl, draw])

  // Redraw on state changes
  useEffect(() => {
    if (imageRef.current) draw()
  }, [draw])

  // Resize observer
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver(() => {
      if (imageRef.current) draw()
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [draw])

  const getCanvasCoords = (e: React.MouseEvent) => {
    const rect = canvasRef.current!.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  return (
    <div ref={containerRef} className="w-full">
      <canvas
        ref={canvasRef}
        className="w-full rounded cursor-crosshair"
        onMouseMove={e => {
          const { x, y } = getCanvasCoords(e)
          onHover(x, y, detections, scaleRef.current)
        }}
        onMouseLeave={() => onHover(-1, -1, detections, scaleRef.current)}
        onClick={e => {
          const { x, y } = getCanvasCoords(e)
          onClick(x, y, detections, scaleRef.current)
        }}
      />
    </div>
  )
}
