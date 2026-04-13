import { useState, useEffect, useCallback } from 'react'
import type { MobileBbox, StoredImage } from '../types'
import { getNextUnannotated, saveAnnotation, getAnnotation, getStats } from '../lib/db'
import { generateId } from '../lib/id'
import TouchCanvas from '../components/TouchCanvas'
import BottomToolbar from '../components/BottomToolbar'
import PredictionCards from '../components/PredictionCards'

interface Props {
  onBack: () => void
}

interface Rect { x: number; y: number; width: number; height: number }

// Faction label remapping — mirrors annotationService.ts EXPORT_LABEL_REMAP.
// When the imported batch's faction is one of these, default the label to the
// canonical class so annotators don't accidentally re-introduce split classes.
const FACTION_REMAP: Record<string, string> = {
  // Loyalist chapters → space_marines
  blood_angels:     'space_marines',
  dark_angels:      'space_marines',
  space_wolves:     'space_marines',
  black_templars:   'space_marines',
  deathwatch:       'space_marines',
  grey_knights:     'space_marines',
  // Traitor legions → chaos_space_marines
  death_guard:      'chaos_space_marines',
  thousand_sons:    'chaos_space_marines',
  world_eaters:     'chaos_space_marines',
  emperors_children:'chaos_space_marines',
}

// Canonical faction list shown in the label picker.
// Collapsed subfactions are omitted — their images are labelled under the parent class.
const DEFAULT_FACTIONS = [
  // Imperium
  'space_marines', 'adeptus_mechanicus', 'imperial_guard',
  'custodes', 'adepta_sororitas', 'imperial_knights', 'imperial_agents',
  // Chaos
  'chaos_space_marines', 'chaos_daemons', 'chaos_knights',
  // Xenos
  'orks', 'eldar', 'drukhari', 'harlequins', 'ynnari',
  'tau_empire', 'tyranids', 'genestealer_cult', 'necrons', 'leagues_of_votann',
]

function haptic() {
  try { navigator.vibrate?.(10) } catch { /* not supported */ }
}

export default function AnnotatePage({ onBack }: Props) {
  const [image, setImage] = useState<StoredImage | null>(null)
  const [bboxes, setBboxes] = useState<MobileBbox[]>([])
  const [classLabel, setClassLabel] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [allDone, setAllDone] = useState(false)
  const [progress, setProgress] = useState({ current: 0, total: 0 })
  const [factions, setFactions] = useState<string[]>(DEFAULT_FACTIONS)

  // Pending bbox — drawn but not yet confirmed
  const [pendingBbox, setPendingBbox] = useState<Rect | null>(null)

  // Prediction tracking
  const [acceptedPredictionIds, setAcceptedPredictionIds] = useState<Set<string>>(new Set())
  const [rejectedPredictionIds, setRejectedPredictionIds] = useState<Set<string>>(new Set())
  const [highlightPredictionIndex, setHighlightPredictionIndex] = useState<number | null>(null)

  const loadNext = useCallback(async () => {
    setLoading(true)
    setBboxes([])
    setPendingBbox(null)
    setAcceptedPredictionIds(new Set())
    setRejectedPredictionIds(new Set())
    setHighlightPredictionIndex(null)

    const stats = await getStats()
    setProgress({ current: stats.annotated, total: stats.totalImages })

    const next = await getNextUnannotated()
    if (!next) {
      setAllDone(true)
      setLoading(false)
      return
    }

    setImage(next)
    setClassLabel(FACTION_REMAP[next.faction] ?? next.faction)

    // Update faction list if needed
    if (!factions.includes(next.faction)) {
      setFactions(prev => [...prev, next.faction].sort())
    }

    // Restore in-progress draft if one exists
    const draft = await getAnnotation(next.imageId)
    if (draft && !draft.completed && draft.bboxes.length > 0) {
      setBboxes(draft.bboxes)
    }

    setLoading(false)
  }, [factions])

  useEffect(() => { loadNext() }, [])

  // Auto-save draft whenever confirmed bboxes change (guards against loading transitions)
  useEffect(() => {
    if (!image || loading) return
    saveAnnotation(image.imageId, bboxes, false, image.width, image.height).catch(() => {})
  }, [bboxes, image, loading])

  // Called by TouchCanvas when user finishes dragging a rectangle
  const handleDrawComplete = useCallback((rect: Rect) => {
    setPendingBbox(rect)
  }, [])

  // Confirm the pending bbox → add to committed list
  const handleConfirmBbox = useCallback(() => {
    if (!pendingBbox) return
    haptic()
    const newBbox: MobileBbox = {
      id: generateId(),
      x: pendingBbox.x,
      y: pendingBbox.y,
      width: pendingBbox.width,
      height: pendingBbox.height,
      classLabel,
      fromPrediction: false,
    }
    setBboxes(prev => [...prev, newBbox])
    setPendingBbox(null)
  }, [pendingBbox, classLabel])

  // Cancel the pending bbox
  const handleCancelBbox = useCallback(() => {
    setPendingBbox(null)
  }, [])

  // Undo: remove last committed bbox (or cancel pending)
  const handleUndo = useCallback(() => {
    if (pendingBbox) {
      setPendingBbox(null)
    } else {
      setBboxes(prev => prev.slice(0, -1))
    }
  }, [pendingBbox])

  const handleSave = useCallback(async () => {
    if (!image || saving) return
    haptic()
    setSaving(true)
    try {
      // All boxes in an image belong to one army — stamp the current faction onto every bbox
      const labeledBboxes = bboxes.map(b => ({ ...b, classLabel }))
      await saveAnnotation(image.imageId, labeledBboxes, true, image.width, image.height)
      loadNext()
    } finally {
      setSaving(false)
    }
  }, [image, bboxes, loadNext, saving])

  const handleSkip = useCallback(async () => {
    if (!image || saving) return
    setSaving(true)
    try {
      await saveAnnotation(image.imageId, [], true, image.width, image.height, true)
      loadNext()
    } finally {
      setSaving(false)
    }
  }, [image, loadNext, saving])

  const handleAcceptPrediction = useCallback((index: number) => {
    if (!image?.predictions) return
    const pred = image.predictions[index]
    const predId = `pred-${index}`

    setAcceptedPredictionIds(prev => new Set(prev).add(predId))

    const newBbox: MobileBbox = {
      id: generateId(),
      x: pred.x,
      y: pred.y,
      width: pred.width,
      height: pred.height,
      classLabel: pred.classLabel,
      fromPrediction: true,
      confidence: pred.confidence,
    }
    setBboxes(prev => [...prev, newBbox])
  }, [image])

  const handleRejectPrediction = useCallback((index: number) => {
    const predId = `pred-${index}`
    setRejectedPredictionIds(prev => new Set(prev).add(predId))
  }, [])

  const handleAcceptAll = useCallback(() => {
    if (!image?.predictions) return
    image.predictions.forEach((pred, i) => {
      const predId = `pred-${i}`
      if (!acceptedPredictionIds.has(predId) && !rejectedPredictionIds.has(predId)) {
        handleAcceptPrediction(i)
      }
    })
  }, [image, acceptedPredictionIds, rejectedPredictionIds, handleAcceptPrediction])

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-gothic-light font-grim animate-pulse">Loading...</div>
      </div>
    )
  }

  if (allDone) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
        <div className="text-4xl mb-4">&#9876;</div>
        <h2 className="font-gothic text-xl font-bold text-glow mb-2">ALL DONE</h2>
        <p className="text-gothic-light text-sm mb-6">Every image has been annotated. The Emperor protects.</p>
        <button
          onClick={onBack}
          className="px-6 py-3 rounded-lg bg-blue-600 text-white font-gothic font-bold tracking-wider shadow-glow-md active:scale-95 transition-all"
        >
          RETURN HOME
        </button>
      </div>
    )
  }

  if (!image) return null

  const visiblePredictions = (image.predictions || []).filter((_, i) => {
    const predId = `pred-${i}`
    return !acceptedPredictionIds.has(predId) && !rejectedPredictionIds.has(predId)
  })

  const canUndo = pendingBbox !== null || bboxes.length > 0

  return (
    <div className="flex flex-col h-[100dvh]">
      {/* Header */}
      <div className="flex items-center px-3 py-1 bg-gothic-darker safe-top">
        <button
          onClick={onBack}
          className="text-gothic-light text-xs font-grim active:text-white transition-colors"
        >
          &larr; BACK
        </button>
        <span className="ml-auto text-xs text-gothic-light font-grim truncate max-w-[60%]">
          {image.faction.replace(/_/g, ' ')}
        </span>
      </div>

      {/* Canvas */}
      <TouchCanvas
        imageBlob={image.blob}
        imageWidth={image.width}
        imageHeight={image.height}
        bboxes={bboxes}
        predictions={image.predictions || []}
        acceptedPredictionIds={acceptedPredictionIds}
        rejectedPredictionIds={rejectedPredictionIds}
        highlightPredictionIndex={highlightPredictionIndex}
        pendingBbox={pendingBbox}
        onDrawComplete={handleDrawComplete}
      />

      {/* Confirm / Cancel bar — appears when a bbox is drawn but not yet confirmed */}
      {pendingBbox && (
        <div className="flex items-center gap-2 px-2 py-1.5 bg-gothic-darker border-t border-yellow-500/30">
          <button
            onClick={handleCancelBbox}
            className="flex-1 py-1.5 rounded-lg bg-red-600 text-white font-gothic text-xs font-bold tracking-wider active:scale-95 transition-all min-h-[36px]"
          >
            REDRAW
          </button>
          <button
            onClick={handleConfirmBbox}
            className="flex-[2] py-1.5 rounded-lg bg-green-600 text-white font-gothic text-sm font-bold tracking-wider active:scale-95 transition-all shadow-glow-sm min-h-[36px]"
          >
            CONFIRM BOX
          </button>
        </div>
      )}

      {/* Prediction cards */}
      {visiblePredictions.length > 0 && (
        <PredictionCards
          predictions={image.predictions || []}
          acceptedIds={acceptedPredictionIds}
          rejectedIds={rejectedPredictionIds}
          onAccept={handleAcceptPrediction}
          onReject={handleRejectPrediction}
          onAcceptAll={handleAcceptAll}
          onHighlight={setHighlightPredictionIndex}
        />
      )}

      {/* Bottom toolbar */}
      <BottomToolbar
        classLabel={classLabel}
        onClassChange={setClassLabel}
        onUndo={handleUndo}
        onSkip={handleSkip}
        onSave={handleSave}
        canUndo={canUndo}
        progress={progress}
        factions={factions}
      />
    </div>
  )
}
