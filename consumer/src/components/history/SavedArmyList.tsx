import type { Army } from '../../types/army'
import SavedArmyCard from './SavedArmyCard'

interface SavedArmyListProps {
  armies: Army[]
  onSelect: (army: Army) => void
  onDelete: (id: string) => void
}

export default function SavedArmyList({ armies, onSelect, onDelete }: SavedArmyListProps) {
  if (armies.length === 0) return null

  return (
    <div className="mt-8">
      <h3 className="font-gothic text-lg text-gray-200 mb-3">Saved Armies</h3>
      <div className="grid grid-cols-3 gap-4">
        {armies.map(army => (
          <SavedArmyCard
            key={army.id}
            army={army}
            onClick={() => onSelect(army)}
            onDelete={() => onDelete(army.id)}
          />
        ))}
      </div>
    </div>
  )
}
