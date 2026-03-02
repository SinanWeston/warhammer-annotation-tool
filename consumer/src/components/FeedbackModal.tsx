import { useState } from 'react'
import { FACTIONS } from '../utils/factions'
import FactionIcon from './FactionIcon'

interface FeedbackModalProps {
  originalFaction: string
  onSubmit: (correctedFaction: string | null) => void
  onCancel: () => void
}

export default function FeedbackModal({ originalFaction, onSubmit, onCancel }: FeedbackModalProps) {
  const [selected, setSelected] = useState<string | null | undefined>(undefined)

  const handleSubmit = () => {
    if (selected === undefined) return
    onSubmit(selected)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-gothic-dark border border-gothic-medium/40 rounded-2xl max-w-sm w-full max-h-[80dvh] flex flex-col">
        {/* Header */}
        <div className="p-5 pb-3 border-b border-gothic-medium/20">
          <h3 className="font-gothic text-lg text-white">Report Wrong Detection</h3>
          <p className="text-gothic-light/50 text-xs font-grim mt-1">
            What is the correct faction?
          </p>
        </div>

        {/* Options */}
        <div className="flex-1 overflow-y-auto p-4 space-y-1.5">
          {/* Not a miniature option */}
          <button
            onClick={() => setSelected(null)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-colors min-h-[44px] ${
              selected === null
                ? 'border-red-500/50 bg-red-500/10'
                : 'border-gothic-medium/20 hover:border-gothic-medium/40'
            }`}
          >
            <div className="w-5 h-5 rounded flex items-center justify-center bg-red-500/20 border border-red-500/40 text-red-400 text-xs shrink-0">
              &#10005;
            </div>
            <span className="text-sm font-grim text-gray-300">Not a miniature</span>
          </button>

          {/* Faction options */}
          {FACTIONS.filter(f => f.key !== originalFaction).map(f => (
            <button
              key={f.key}
              onClick={() => setSelected(f.key)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-colors min-h-[44px] ${
                selected === f.key
                  ? `border-[${f.color}] bg-[${f.color}]/10`
                  : 'border-gothic-medium/20 hover:border-gothic-medium/40'
              }`}
              style={selected === f.key ? { borderColor: `${f.color}80`, backgroundColor: `${f.color}15` } : {}}
            >
              <FactionIcon faction={f.key} color={f.color} size={20} />
              <span className="text-sm font-grim text-gray-300">{f.displayName}</span>
            </button>
          ))}
        </div>

        {/* Actions */}
        <div className="p-4 pt-3 border-t border-gothic-medium/20 flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-3 rounded-lg bg-gothic-dark/60 border border-gothic-medium/30 text-gothic-light font-grim text-sm uppercase tracking-wider hover:bg-gothic-dark/80 transition-colors min-h-[48px]"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={selected === undefined}
            className="flex-1 py-3 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-30 disabled:hover:bg-amber-600 text-white font-grim text-sm uppercase tracking-wider transition-colors min-h-[48px]"
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  )
}
