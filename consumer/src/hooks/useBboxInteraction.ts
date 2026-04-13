import { useCallback, useRef } from 'react'
import type { Detection, BBox } from '../types/detection'
import { useScanStore } from '../stores/scanStore'

export function useBboxInteraction() {
  const highlightedId = useScanStore(s => s.highlightedDetectionId)
  const selectedId = useScanStore(s => s.selectedDetectionId)
  const setHighlighted = useScanStore(s => s.setHighlightedDetection)
  const setSelected = useScanStore(s => s.setSelectedDetection)
  const cardRefs = useRef<Map<string, HTMLDivElement>>(new Map())

  const hitTest = useCallback(
    (canvasX: number, canvasY: number, detections: Detection[], scale: number): Detection | null => {
      // Walk backwards so topmost (last drawn) is found first
      for (let i = detections.length - 1; i >= 0; i--) {
        const d = detections[i]
        const b = d.bbox
        const sx = b.x * scale
        const sy = b.y * scale
        const sw = b.width * scale
        const sh = b.height * scale
        if (canvasX >= sx && canvasX <= sx + sw && canvasY >= sy && canvasY <= sy + sh) {
          return d
        }
      }
      return null
    },
    []
  )

  const scrollToCard = useCallback((id: string) => {
    const el = cardRefs.current.get(id)
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [])

  const onCanvasHover = useCallback(
    (canvasX: number, canvasY: number, detections: Detection[], scale: number) => {
      const hit = hitTest(canvasX, canvasY, detections, scale)
      setHighlighted(hit?.id ?? null)
    },
    [hitTest, setHighlighted]
  )

  const onCanvasClick = useCallback(
    (canvasX: number, canvasY: number, detections: Detection[], scale: number) => {
      const hit = hitTest(canvasX, canvasY, detections, scale)
      if (hit) {
        setSelected(hit.id)
        scrollToCard(hit.id)
      } else {
        setSelected(null)
      }
    },
    [hitTest, setSelected, scrollToCard]
  )

  const onCardHover = useCallback((id: string | null) => setHighlighted(id), [setHighlighted])
  const onCardClick = useCallback((id: string) => setSelected(id), [setSelected])

  const registerCardRef = useCallback((id: string, el: HTMLDivElement | null) => {
    if (el) cardRefs.current.set(id, el)
    else cardRefs.current.delete(id)
  }, [])

  return {
    highlightedId,
    selectedId,
    onCanvasHover,
    onCanvasClick,
    onCardHover,
    onCardClick,
    registerCardRef,
  }
}
