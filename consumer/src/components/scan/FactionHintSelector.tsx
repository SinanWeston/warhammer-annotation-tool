import { useScanStore } from '../../stores/scanStore'
import { FACTIONS } from '../../utils/factions'

export default function FactionHintSelector() {
  const factionHint = useScanStore(s => s.factionHint)
  const setFactionHint = useScanStore(s => s.setFactionHint)

  return (
    <div className="flex items-center gap-3">
      <label className="text-sm text-gothic-light font-grim whitespace-nowrap">
        Faction hint (optional):
      </label>
      <select
        value={factionHint ?? ''}
        onChange={e => setFactionHint(e.target.value || undefined)}
        className="bg-surface-2 border border-surface-3 rounded px-3 py-1.5 text-sm text-gray-200
                   font-grim focus:outline-none focus:border-brass"
      >
        <option value="">Auto-detect all</option>
        {FACTIONS.map(f => (
          <option key={f.key} value={f.key}>{f.displayName}</option>
        ))}
      </select>
    </div>
  )
}
