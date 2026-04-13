import type { PlaystyleTag } from '../../types/army'

interface PlaystyleFilterProps {
  active: PlaystyleTag | null
  onChange: (tag: PlaystyleTag | null) => void
}

const styles: { key: PlaystyleTag; label: string }[] = [
  { key: 'aggressive', label: 'Aggressive' },
  { key: 'defensive', label: 'Defensive' },
  { key: 'balanced', label: 'Balanced' },
  { key: 'competitive', label: 'Competitive' },
]

export default function PlaystyleFilter({ active, onChange }: PlaystyleFilterProps) {
  return (
    <div className="flex gap-2">
      {styles.map(s => (
        <button
          key={s.key}
          onClick={() => onChange(active === s.key ? null : s.key)}
          className={`px-3 py-1 text-xs font-grim rounded border transition-colors ${
            active === s.key
              ? 'border-brass bg-brass/20 text-brass-light'
              : 'border-surface-3 text-gothic-light hover:border-gothic-medium hover:text-gray-300'
          }`}
        >
          {s.label}
        </button>
      ))}
    </div>
  )
}
