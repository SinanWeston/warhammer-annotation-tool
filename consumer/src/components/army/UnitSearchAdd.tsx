import { useState, useMemo } from 'react'
import { UNIT_DATABASE } from '../../data/units'
import { useArmyStore } from '../../stores/armyStore'
import { getFactionDisplayName } from '../../utils/factions'
import { getRoleLabel } from '../../data/battlefieldRoles'
import FactionIcon from '../FactionIcon'

export default function UnitSearchAdd() {
  const [query, setQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const addUnit = useArmyStore(s => s.addUnit)

  const results = useMemo(() => {
    if (query.length < 2) return []
    const q = query.toLowerCase()
    return UNIT_DATABASE
      .filter(u =>
        u.name.toLowerCase().includes(q) ||
        u.faction.toLowerCase().includes(q) ||
        u.keywords.some(k => k.includes(q))
      )
      .slice(0, 15)
  }, [query])

  const handleAdd = (unit: typeof UNIT_DATABASE[number]) => {
    addUnit({
      unitName: unit.name,
      faction: unit.faction,
      role: unit.role,
      count: unit.minModels,
      pointsPerModel: unit.pointsPerModel,
    })
    setQuery('')
    setIsOpen(false)
  }

  return (
    <div className="relative">
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={e => { setQuery(e.target.value); setIsOpen(true) }}
          onFocus={() => setIsOpen(true)}
          placeholder="Search units to add..."
          className="flex-1 bg-surface-2 border border-surface-3 rounded px-3 py-2 text-sm text-gray-200
                     font-grim placeholder:text-gothic-light focus:outline-none focus:border-brass"
        />
      </div>

      {isOpen && results.length > 0 && (
        <div className="absolute z-20 top-full mt-1 w-full bg-surface-1 border border-surface-3 rounded-lg shadow-lg max-h-80 overflow-y-auto scrollbar-thin">
          {results.map((unit, i) => (
            <button
              key={`${unit.faction}-${unit.name}-${i}`}
              onClick={() => handleAdd(unit)}
              className="w-full text-left px-3 py-2.5 hover:bg-surface-2 flex items-center gap-3 border-b border-surface-3 last:border-0"
            >
              <FactionIcon faction={unit.faction} size="sm" />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-gray-200">{unit.name}</div>
                <div className="text-[10px] text-gothic-light font-grim">
                  {getFactionDisplayName(unit.faction)} — {getRoleLabel(unit.role)} — {unit.pointsPerModel} pts/model
                </div>
              </div>
              <span className="text-xs text-brass font-grim shrink-0">
                + Add
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Close dropdown on outside click */}
      {isOpen && (
        <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
      )}
    </div>
  )
}
