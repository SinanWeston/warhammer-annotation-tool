import { useMemo } from 'react'
import type { Detection, GroupingMode } from '../../types/detection'
import UnitCard from './UnitCard'
import UncertainSection from './UncertainSection'
import GroupingToggle from './GroupingToggle'
import { getFactionDisplayName } from '../../utils/factions'
import { getRoleLabel } from '../../data/battlefieldRoles'

const CONFIDENCE_THRESHOLD = 0.5

interface UnitListProps {
  detections: Detection[]
  groupingMode: GroupingMode
  onGroupingChange: (mode: GroupingMode) => void
  highlightedId: string | null
  selectedId: string | null
  onHover: (id: string | null) => void
  onClick: (id: string) => void
  registerRef: (id: string, el: HTMLDivElement | null) => void
}

export default function UnitList({
  detections, groupingMode, onGroupingChange,
  highlightedId, selectedId, onHover, onClick, registerRef
}: UnitListProps) {
  const { confident, uncertain } = useMemo(() => {
    const confident: Detection[] = []
    const uncertain: Detection[] = []
    for (const d of detections) {
      if (d.confidence >= CONFIDENCE_THRESHOLD) confident.push(d)
      else uncertain.push(d)
    }
    return { confident, uncertain }
  }, [detections])

  const grouped = useMemo(() => {
    if (groupingMode === 'flat') return [{ key: 'all', label: 'All Detections', items: confident }]

    const map = new Map<string, Detection[]>()
    for (const d of confident) {
      const key = groupingMode === 'faction' ? d.faction : d.role
      const list = map.get(key) || []
      list.push(d)
      map.set(key, list)
    }

    return Array.from(map.entries()).map(([key, items]) => ({
      key,
      label: groupingMode === 'faction' ? getFactionDisplayName(key) : getRoleLabel(key),
      items,
    }))
  }, [confident, groupingMode])

  const totalPoints = detections.reduce((sum, d) => sum + d.points, 0)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-gothic text-lg text-gray-200">
            {detections.length} Detection{detections.length !== 1 ? 's' : ''}
          </h3>
          <span className="text-xs text-brass font-grim">{totalPoints} pts total</span>
        </div>
        <GroupingToggle mode={groupingMode} onChange={onGroupingChange} />
      </div>

      {grouped.map(group => (
        <div key={group.key} className="mb-4">
          {groupingMode !== 'flat' && (
            <h4 className="text-xs font-grim text-gothic-light uppercase mb-2 tracking-wider">
              {group.label} ({group.items.length})
            </h4>
          )}
          <div className="space-y-2">
            {group.items.map(d => (
              <UnitCard
                key={d.id}
                detection={d}
                isHighlighted={highlightedId === d.id}
                isSelected={selectedId === d.id}
                onHover={onHover}
                onClick={onClick}
                registerRef={registerRef}
              />
            ))}
          </div>
        </div>
      ))}

      <UncertainSection
        detections={uncertain}
        highlightedId={highlightedId}
        selectedId={selectedId}
        onHover={onHover}
        onClick={onClick}
        registerRef={registerRef}
      />
    </div>
  )
}
