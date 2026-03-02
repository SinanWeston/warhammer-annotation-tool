import { useRef, useEffect } from 'react'

interface Props {
  classLabel: string
  onClassChange: (label: string) => void
  onUndo: () => void
  onSkip: () => void
  onSave: () => void
  canUndo: boolean
  progress: { current: number; total: number }
  factions: string[]
}

export default function BottomToolbar({
  classLabel,
  onClassChange,
  onUndo,
  onSkip,
  onSave,
  canUndo,
  progress,
  factions,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null)

  // Scroll active chip into view
  useEffect(() => {
    const el = scrollRef.current?.querySelector('[data-active="true"]')
    el?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  }, [classLabel])

  return (
    <div className="bg-gothic-darker border-t border-gothic-medium/30 safe-bottom">
      {/* Class selector */}
      <div
        ref={scrollRef}
        className="flex gap-1.5 px-2 py-1 overflow-x-auto scrollbar-hide"
        style={{ WebkitOverflowScrolling: 'touch' }}
      >
        {factions.map((f) => (
          <button
            key={f}
            data-active={f === classLabel ? 'true' : 'false'}
            onClick={() => onClassChange(f)}
            className={`flex-shrink-0 px-2.5 py-1 rounded-full text-xs font-grim tracking-wider transition-all min-h-[32px] ${
              f === classLabel
                ? 'bg-blue-600 text-white shadow-glow-sm'
                : 'bg-gothic-dark/60 text-gothic-light border border-gothic-medium/30'
            }`}
          >
            {f.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {/* Action buttons + progress */}
      <div className="flex items-center gap-1.5 px-2 pb-1.5 pt-0.5">
        <button
          onClick={onUndo}
          disabled={!canUndo}
          className="px-3 py-1.5 rounded-lg bg-gothic-dark border border-gothic-medium/30 text-xs font-grim disabled:opacity-30 active:scale-95 transition-all min-h-[36px]"
        >
          UNDO
        </button>

        <button
          onClick={onSkip}
          className="px-3 py-1.5 rounded-lg bg-gothic-dark border border-gothic-medium/30 text-xs font-grim active:scale-95 transition-all min-h-[36px]"
        >
          SKIP
        </button>

        <button
          onClick={onSave}
          className="flex-1 py-1.5 rounded-lg bg-blue-600 text-white font-gothic text-sm font-bold tracking-wider shadow-glow-sm active:scale-[0.97] transition-all min-h-[36px]"
        >
          SAVE & NEXT
        </button>

        <span className="text-xs text-gothic-light font-grim whitespace-nowrap pl-1">
          {progress.current}/{progress.total}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-0.5 bg-gothic-dark/60 overflow-hidden">
        <div
          className="h-full bg-blue-500 transition-all"
          style={{ width: `${progress.total > 0 ? (progress.current / progress.total) * 100 : 0}%` }}
        />
      </div>
    </div>
  )
}
