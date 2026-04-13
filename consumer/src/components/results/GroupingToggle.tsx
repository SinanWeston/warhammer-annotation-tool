import type { GroupingMode } from '../../types/detection'

interface GroupingToggleProps {
  mode: GroupingMode
  onChange: (mode: GroupingMode) => void
}

const modes: { key: GroupingMode; label: string }[] = [
  { key: 'faction', label: 'Faction' },
  { key: 'role', label: 'Role' },
  { key: 'flat', label: 'Flat' },
]

export default function GroupingToggle({ mode, onChange }: GroupingToggleProps) {
  return (
    <div className="flex bg-surface-2 rounded p-0.5">
      {modes.map(m => (
        <button
          key={m.key}
          onClick={() => onChange(m.key)}
          className={`px-3 py-1 text-xs font-grim rounded transition-colors ${
            mode === m.key
              ? 'bg-brass text-gothic-darker'
              : 'text-gothic-light hover:text-gray-300'
          }`}
        >
          {m.label}
        </button>
      ))}
    </div>
  )
}
