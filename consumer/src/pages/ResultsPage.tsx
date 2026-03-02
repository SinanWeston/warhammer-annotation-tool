import { useRef, useEffect, useState } from 'react'
import ArmySummary from '../components/ArmySummary'
import ResultsCard from '../components/ResultsCard'
import FeedbackModal from '../components/FeedbackModal'
import { DetectionResult } from '../types/detection'
import { formatFactionName } from '../utils/factionDisplay'
import { saveFeedback, getUnsyncedFeedback, markFeedbackSynced } from '../lib/db'

interface ResultsPageProps {
  results: DetectionResult
  scannedImage: string
  scanId: string | null
  onScanAnother: () => void
  onAddToArmy?: () => void
}

export default function ResultsPage({ results, scannedImage, scanId, onScanAnother, onAddToArmy }: ResultsPageProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [minConfidence, setMinConfidence] = useState(0.4)
  const [feedbackTarget, setFeedbackTarget] = useState<{ detectionIndex: number; faction: string } | null>(null)

  // 2.4 — Proper empty state
  if (results.totalDetected === 0) {
    return (
      <div className="w-full flex flex-col items-center gap-6 animate-fade-in-down pt-4">
        <div className="w-full rounded-xl overflow-hidden border-2 border-gothic-dark/60 opacity-40">
          <img src={scannedImage} alt="Scanned" className="w-full h-auto" />
        </div>
        <div className="text-center">
          <p className="text-white font-gothic text-xl">No miniatures detected</p>
          <p className="text-gothic-light/60 text-sm mt-2">Try a closer photo with better lighting</p>
        </div>
        <button
          onClick={onScanAnother}
          className="w-full py-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-grim text-sm uppercase tracking-wider shadow-glow-blue transition-all min-h-[48px]"
        >
          Try Again
        </button>
      </div>
    )
  }

  // 2.3 — Filter detections by confidence
  const filteredDetections = results.detections.filter(d => d.confidence >= minConfidence)

  const filteredSummary = results.summary
    .map(s => {
      const dets = filteredDetections.filter(d => d.faction === s.faction)
      if (dets.length === 0) return null
      return {
        ...s,
        count: dets.length,
        avgConfidence: dets.reduce((sum, d) => sum + d.confidence, 0) / dets.length,
      }
    })
    .filter((s): s is NonNullable<typeof s> => s !== null)

  const filteredResults: DetectionResult = {
    ...results,
    detections: filteredDetections,
    summary: filteredSummary,
    totalDetected: filteredDetections.length,
  }

  // Canvas drawing with bbox overlay
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const toShow = results.detections.filter(d => d.confidence >= minConfidence)

    const img = new Image()
    img.onload = () => {
      canvas.width = img.width
      canvas.height = img.height
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      ctx.drawImage(img, 0, 0)

      for (const det of toShow) {
        const color = results.summary.find(s => s.faction === det.faction)?.color || '#60a5fa'
        ctx.strokeStyle = color
        ctx.lineWidth = Math.max(2, img.width / 400)
        ctx.strokeRect(det.bbox.x, det.bbox.y, det.bbox.width, det.bbox.height)

        // 3.2 — Formatted label with clamped position
        const label = `${formatFactionName(det.faction)} ${Math.round(det.confidence * 100)}%`
        const fontSize = Math.max(12, img.width / 60)
        ctx.font = `bold ${fontSize}px sans-serif`
        const textMetrics = ctx.measureText(label)
        const textHeight = Math.max(14, img.width / 50)
        const padding = 4

        const labelX = Math.min(det.bbox.x, canvas.width - textMetrics.width - padding * 2)
        const labelY =
          det.bbox.y > textHeight + padding * 2
            ? det.bbox.y - padding
            : det.bbox.y + det.bbox.height + textHeight + padding * 2

        ctx.fillStyle = color
        ctx.fillRect(labelX, labelY - textHeight - padding, textMetrics.width + padding * 2, textHeight + padding * 2)
        ctx.fillStyle = '#000'
        ctx.fillText(label, labelX + padding, labelY)
      }
    }
    img.src = scannedImage
  }, [results, scannedImage, minConfidence])

  // 3.4 — Share via Web Share API with canvas image
  const handleShare = async () => {
    const canvas = canvasRef.current
    if (!canvas) return

    canvas.toBlob(async (blob) => {
      if (!blob) return
      const file = new File([blob], 'army-scan.png', { type: 'image/png' })
      const summary = filteredResults.summary
        .map(s => `${formatFactionName(s.faction)}: ${s.count}`)
        .join(', ')

      try {
        if (navigator.canShare?.({ files: [file] })) {
          await navigator.share({
            title: 'My Warhammer Army Scan',
            text: `Battle Scanner detected ${filteredResults.totalDetected} miniatures — ${summary}`,
            files: [file],
          })
        } else {
          const a = document.createElement('a')
          a.href = canvas.toDataURL('image/png')
          a.download = 'army-scan.png'
          a.click()
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') console.error('Share failed', err)
      }
    }, 'image/png')
  }

  // Feedback handlers
  const handleReportWrong = (detectionIndex: number, faction: string) => {
    setFeedbackTarget({ detectionIndex, faction })
  }

  const handleFeedbackSubmit = async (correctedFaction: string | null) => {
    if (!feedbackTarget || !scanId) return

    // Save to IndexedDB
    await saveFeedback(scanId, feedbackTarget.faction, correctedFaction, feedbackTarget.detectionIndex)
    setFeedbackTarget(null)

    // Attempt to sync unsynced feedback to backend
    try {
      const unsynced = await getUnsyncedFeedback()
      if (unsynced.length > 0) {
        const res = await fetch('/api/consumer/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feedback: unsynced }),
        })
        if (res.ok) {
          await markFeedbackSynced(unsynced.map(f => f.id))
        }
      }
    } catch {
      // Will sync later
    }
  }

  return (
    <div className="w-full flex flex-col gap-6 animate-fade-in-down pt-4">
      {/* Feedback modal */}
      {feedbackTarget && (
        <FeedbackModal
          originalFaction={feedbackTarget.faction}
          onSubmit={handleFeedbackSubmit}
          onCancel={() => setFeedbackTarget(null)}
        />
      )}

      {/* Scanned image with overlays */}
      <div className="w-full rounded-xl overflow-hidden border-2 border-gothic-dark/60 shadow-glow-sm">
        <canvas ref={canvasRef} className="w-full h-auto" />
      </div>

      {/* 2.2 — Inference time + detection count */}
      <div className="flex items-center justify-between text-xs font-grim text-gothic-light/50">
        <span>Scanned in {(results.inferenceTimeMs / 1000).toFixed(1)}s</span>
        <span>{filteredDetections.length} of {results.totalDetected} detections shown</span>
      </div>

      {/* 2.3 — Confidence filter slider */}
      <div className="bg-gothic-dark/20 border border-gothic-medium/20 rounded-lg px-4 py-3">
        <div className="flex items-center justify-between mb-2">
          <label className="text-gothic-light/70 text-xs font-grim uppercase tracking-wider">
            Min Confidence
          </label>
          <span className="text-blue-400 text-xs font-grim font-bold">
            {Math.round(minConfidence * 100)}%
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={95}
          step={5}
          value={Math.round(minConfidence * 100)}
          onChange={e => setMinConfidence(Number(e.target.value) / 100)}
          className="w-full accent-blue-400 cursor-pointer"
        />
      </div>

      {/* Army summary */}
      <ArmySummary results={filteredResults} />

      {/* Faction cards */}
      {filteredResults.summary.map(faction => (
        <ResultsCard
          key={faction.faction}
          faction={faction}
          detections={filteredDetections.filter(d => d.faction === faction.faction)}
          onReportWrong={handleReportWrong}
        />
      ))}

      {/* Action bar */}
      <div className="flex gap-3">
        <button
          onClick={handleShare}
          className="flex-1 py-4 rounded-lg bg-gothic-dark/60 border border-gothic-medium/40 text-white font-grim text-sm uppercase tracking-wider hover:bg-gothic-dark/80 transition-all min-h-[48px]"
        >
          Share
        </button>
        {onAddToArmy && (
          <button
            onClick={onAddToArmy}
            className="flex-1 py-4 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-grim text-sm uppercase tracking-wider transition-all min-h-[48px]"
          >
            Add to Army
          </button>
        )}
        <button
          onClick={onScanAnother}
          className="flex-1 py-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-grim text-sm uppercase tracking-wider shadow-glow-blue transition-all min-h-[48px]"
        >
          Scan Another
        </button>
      </div>
    </div>
  )
}
