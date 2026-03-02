import type { PredictionBox } from '../types'

interface Props {
  predictions: PredictionBox[]
  acceptedIds: Set<string>
  rejectedIds: Set<string>
  onAccept: (index: number) => void
  onReject: (index: number) => void
  onAcceptAll: () => void
  onHighlight: (index: number | null) => void
}

export default function PredictionCards({
  predictions,
  acceptedIds,
  rejectedIds,
  onAccept,
  onReject,
  onAcceptAll,
  onHighlight,
}: Props) {
  const visiblePredictions = predictions
    .map((pred, i) => ({ pred, i }))
    .filter(({ i }) => {
      const id = `pred-${i}`
      return !acceptedIds.has(id) && !rejectedIds.has(id)
    })

  if (visiblePredictions.length === 0) return null

  return (
    <div className="bg-gothic-darker/90 border-t border-purple-500/20">
      <div
        className="flex gap-2 px-3 py-2 overflow-x-auto items-center scrollbar-hide"
        style={{ WebkitOverflowScrolling: 'touch' }}
      >
        {visiblePredictions.length > 2 && (
          <button
            onClick={onAcceptAll}
            className="flex-shrink-0 px-4 py-2.5 rounded-lg bg-purple-600/30 border border-purple-500/40 text-purple-300 text-xs font-grim active:scale-95 transition-all min-h-[44px]"
          >
            ALL
          </button>
        )}

        {visiblePredictions.map(({ pred, i }) => (
          <div
            key={i}
            className="flex-shrink-0 flex items-center gap-2 bg-gothic-dark/60 border border-purple-500/30 rounded-lg px-2.5 py-2"
            onPointerEnter={() => onHighlight(i)}
            onPointerLeave={() => onHighlight(null)}
          >
            <span className="text-xs text-purple-300 font-grim truncate max-w-[80px]">
              {pred.classLabel.replace(/_/g, ' ')}
            </span>
            <span className="text-[10px] text-gothic-light font-grim">
              {(pred.confidence * 100).toFixed(0)}%
            </span>
            <button
              onClick={() => onAccept(i)}
              className="w-10 h-10 rounded-lg bg-green-600/30 text-green-400 text-base flex items-center justify-center active:scale-90 transition-all"
              aria-label="Accept"
            >
              &#10003;
            </button>
            <button
              onClick={() => onReject(i)}
              className="w-10 h-10 rounded-lg bg-red-600/30 text-red-400 text-base flex items-center justify-center active:scale-90 transition-all"
              aria-label="Reject"
            >
              &#10005;
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
