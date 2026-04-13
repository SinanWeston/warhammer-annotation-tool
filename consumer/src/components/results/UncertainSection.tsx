import type { Detection } from '../../types/detection'
import UnitCard from './UnitCard'

interface UncertainSectionProps {
  detections: Detection[]
  highlightedId: string | null
  selectedId: string | null
  onHover: (id: string | null) => void
  onClick: (id: string) => void
  registerRef: (id: string, el: HTMLDivElement | null) => void
}

export default function UncertainSection({
  detections, highlightedId, selectedId, onHover, onClick, registerRef
}: UncertainSectionProps) {
  if (detections.length === 0) return null

  return (
    <div className="mt-4 pt-4 border-t border-surface-3">
      <h4 className="text-xs font-grim text-orange-400 uppercase mb-2">
        Uncertain Detections ({detections.length})
      </h4>
      <div className="space-y-2">
        {detections.map(d => (
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
  )
}
