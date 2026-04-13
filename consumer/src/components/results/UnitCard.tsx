import { useState } from 'react'
import type { Detection } from '../../types/detection'
import FactionIcon from '../FactionIcon'
import ConfidenceBar from './ConfidenceBar'
import UnitEditInline from './UnitEditInline'
import { getRoleLabel } from '../../data/battlefieldRoles'
import { useScanStore } from '../../stores/scanStore'

interface UnitCardProps {
  detection: Detection
  isHighlighted: boolean
  isSelected: boolean
  onHover: (id: string | null) => void
  onClick: (id: string) => void
  registerRef: (id: string, el: HTMLDivElement | null) => void
}

export default function UnitCard({ detection, isHighlighted, isSelected, onHover, onClick, registerRef }: UnitCardProps) {
  const [editing, setEditing] = useState(false)
  const removeDetection = useScanStore(s => s.removeDetection)

  const borderColor = isSelected
    ? 'border-brass-light'
    : isHighlighted
      ? 'border-gothic-medium'
      : 'border-surface-3'

  return (
    <div
      ref={el => registerRef(detection.id, el)}
      onMouseEnter={() => onHover(detection.id)}
      onMouseLeave={() => onHover(null)}
      onClick={() => onClick(detection.id)}
      className={`bg-surface-2 border ${borderColor} rounded p-3 cursor-pointer transition-colors`}
    >
      <div className="flex items-start gap-3">
        <FactionIcon faction={detection.faction} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-gothic text-gray-200 truncate">{detection.unitName}</h4>
            <span className="text-xs text-brass font-grim ml-2 shrink-0">{detection.points} pts</span>
          </div>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-[10px] text-gothic-light font-grim uppercase">
              {getRoleLabel(detection.role)}
            </span>
            <ConfidenceBar confidence={detection.confidence} />
          </div>
        </div>
      </div>

      {/* Edit/Remove controls on selected */}
      {isSelected && !editing && (
        <div className="flex gap-2 mt-2 pt-2 border-t border-surface-3">
          <button
            onClick={e => { e.stopPropagation(); setEditing(true) }}
            className="px-2 py-1 text-[11px] text-gothic-light hover:text-gray-300 font-grim"
          >
            Edit
          </button>
          <button
            onClick={e => { e.stopPropagation(); removeDetection(detection.id) }}
            className="px-2 py-1 text-[11px] text-red-400 hover:text-red-300 font-grim"
          >
            Remove
          </button>
        </div>
      )}

      {editing && (
        <UnitEditInline detection={detection} onClose={() => setEditing(false)} />
      )}
    </div>
  )
}
