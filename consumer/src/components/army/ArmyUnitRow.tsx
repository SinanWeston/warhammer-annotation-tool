import type { ArmyUnit } from '../../types/army'
import FactionIcon from '../FactionIcon'
import { getRoleLabel } from '../../data/battlefieldRoles'
import { useArmyStore } from '../../stores/armyStore'

interface ArmyUnitRowProps {
  unit: ArmyUnit
}

export default function ArmyUnitRow({ unit }: ArmyUnitRowProps) {
  const updateCount = useArmyStore(s => s.updateUnitCount)
  const removeUnit = useArmyStore(s => s.removeUnit)
  const totalPts = unit.count * unit.pointsPerModel

  return (
    <div className="flex items-center gap-3 bg-surface-2 border border-surface-3 rounded p-3">
      <FactionIcon faction={unit.faction} size="sm" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-200 truncate font-gothic">{unit.unitName}</span>
          <span className="text-xs text-brass font-grim ml-2 shrink-0">{totalPts} pts</span>
        </div>
        <span className="text-[10px] text-gothic-light font-grim uppercase">
          {getRoleLabel(unit.role)} — {unit.pointsPerModel} pts/model
        </span>
      </div>
      <div className="flex items-center gap-1">
        <button
          onClick={() => updateCount(unit.id, -1)}
          className="w-7 h-7 rounded bg-surface-3 text-gray-300 hover:bg-surface-4 text-sm font-bold"
        >
          -
        </button>
        <span className="w-8 text-center text-sm font-grim text-gray-200">{unit.count}</span>
        <button
          onClick={() => updateCount(unit.id, 1)}
          className="w-7 h-7 rounded bg-surface-3 text-gray-300 hover:bg-surface-4 text-sm font-bold"
        >
          +
        </button>
      </div>
      <button
        onClick={() => removeUnit(unit.id)}
        className="text-gothic-light hover:text-red-400 text-lg leading-none ml-1"
        title="Remove unit"
      >
        &times;
      </button>
    </div>
  )
}
