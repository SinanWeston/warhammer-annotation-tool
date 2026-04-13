import type { Army } from '../../types/army'
import { relativeTime } from '../../utils/time'
import FactionIcon from '../FactionIcon'

interface SavedArmyCardProps {
  army: Army
  onClick: () => void
  onDelete: () => void
}

export default function SavedArmyCard({ army, onClick, onDelete }: SavedArmyCardProps) {
  const factions = [...new Set(army.units.map(u => u.faction))]
  const totalPoints = army.units.reduce((sum, u) => sum + u.count * u.pointsPerModel, 0)

  return (
    <div
      onClick={onClick}
      className="bg-surface-2 border border-surface-3 rounded-lg p-4 cursor-pointer hover:border-gothic-medium transition-colors group"
    >
      <div className="flex items-start justify-between">
        <div>
          <h4 className="text-sm font-gothic text-gray-200">{army.name}</h4>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-brass font-grim">{totalPoints} / {army.pointsLimit} pts</span>
            <span className="text-xs text-gothic-light font-grim">{army.units.length} units</span>
          </div>
        </div>
        <button
          onClick={e => { e.stopPropagation(); onDelete() }}
          className="opacity-0 group-hover:opacity-100 text-gothic-light hover:text-red-400 text-lg transition-opacity"
        >
          &times;
        </button>
      </div>
      <div className="flex items-center justify-between mt-3">
        <div className="flex gap-1">
          {factions.map(f => <FactionIcon key={f} faction={f} size="sm" />)}
        </div>
        <span className="text-[10px] text-gothic-light font-grim">{relativeTime(army.updatedAt)}</span>
      </div>
    </div>
  )
}
