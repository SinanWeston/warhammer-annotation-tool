import { useState, useMemo } from 'react'
import type { PlaystyleTag } from '../../types/army'
import { ARMY_SUGGESTIONS } from '../../data/suggestions'
import { useArmyStore } from '../../stores/armyStore'
import { getFactionDisplayName } from '../../utils/factions'
import FactionIcon from '../FactionIcon'
import PlaystyleFilter from './PlaystyleFilter'

export default function CompositionSuggestions() {
  const [playstyle, setPlaystyle] = useState<PlaystyleTag | null>(null)
  const addUnit = useArmyStore(s => s.addUnit)
  const currentFactions = useArmyStore(s => [...new Set(s.currentArmy.units.map(u => u.faction))])

  const filtered = useMemo(() => {
    let list = ARMY_SUGGESTIONS

    // If army has units, prioritize matching factions
    if (currentFactions.length > 0) {
      list = list.filter(s => currentFactions.includes(s.faction))
    }

    if (playstyle) {
      list = list.filter(s => s.playstyle === playstyle)
    }

    return list.slice(0, 3)
  }, [playstyle, currentFactions])

  const handleApply = (suggestion: typeof ARMY_SUGGESTIONS[number]) => {
    for (const unit of suggestion.suggestedUnits) {
      addUnit({
        unitName: unit.unitName,
        faction: suggestion.faction,
        role: '', // role will be looked up or left generic
        count: unit.count,
        pointsPerModel: Math.round(suggestion.totalPoints / suggestion.suggestedUnits.reduce((s, u) => s + u.count, 0)),
      })
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-gothic text-lg text-gray-200">Suggestions</h3>
        <PlaystyleFilter active={playstyle} onChange={setPlaystyle} />
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-gothic-light">No suggestions match your current filters.</p>
      ) : (
        <div className="space-y-3">
          {filtered.map(s => (
            <div key={s.id} className="bg-surface-2 border border-surface-3 rounded-lg p-4">
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                  <FactionIcon faction={s.faction} size="sm" />
                  <div>
                    <h4 className="text-sm font-gothic text-gray-200">{s.title}</h4>
                    <span className="text-[10px] font-grim text-brass">{s.totalPoints} pts — {s.playstyle}</span>
                  </div>
                </div>
                <button
                  onClick={() => handleApply(s)}
                  className="px-3 py-1 bg-brass/20 border border-brass text-brass-light text-xs font-grim rounded hover:bg-brass/30"
                >
                  Apply
                </button>
              </div>
              <p className="text-xs text-gothic-light mb-2">{s.description}</p>
              <div className="space-y-1">
                {s.suggestedUnits.map((u, i) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <span className="text-gray-300">{u.unitName} x{u.count}</span>
                    <span className="text-gothic-light">{u.reason}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
