import { useState } from 'react'
import { AccumulatedArmy } from '../types/detection'
import FactionIcon from '../components/FactionIcon'
import { formatFactionName } from '../utils/factionDisplay'
import { getPointsPerModel } from '../utils/factions'

interface ArmyPageProps {
  army: AccumulatedArmy | null
  scanCount: number
  onClearArmy: () => void
  onScanMore: () => void
}

export default function ArmyPage({ army, scanCount, onClearArmy, onScanMore }: ArmyPageProps) {
  const [confirmClear, setConfirmClear] = useState(false)

  if (!army || army.totalModels === 0) {
    return (
      <div className="w-full flex flex-col items-center gap-6 pt-12 animate-fade-in-down">
        <div className="w-16 h-16 rounded-full bg-gothic-dark/40 border border-amber-500/20 flex items-center justify-center">
          <svg className="w-8 h-8 text-amber-400/30" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 2l3 7h7l-5.5 4.5L18 21l-6-4.5L6 21l1.5-7.5L2 9h7l3-7z" />
          </svg>
        </div>
        <div className="text-center">
          <p className="text-white font-gothic text-lg">No army built yet</p>
          <p className="text-gothic-light/50 text-sm font-grim mt-1">
            Scan your miniatures and tap "Add to Army" to build your roster
          </p>
        </div>
        <button
          onClick={onScanMore}
          className="px-6 py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-grim text-sm uppercase tracking-wider shadow-glow-blue transition-all min-h-[48px]"
        >
          Start Scanning
        </button>
      </div>
    )
  }

  const totalPoints = army.factions.reduce(
    (sum, f) => sum + getPointsPerModel(f.faction) * f.count,
    0
  )

  const sortedFactions = [...army.factions].sort((a, b) => b.count - a.count)

  const handleClear = () => {
    if (!confirmClear) {
      setConfirmClear(true)
      return
    }
    onClearArmy()
    setConfirmClear(false)
  }

  return (
    <div className="w-full flex flex-col gap-6 animate-fade-in-down pt-4">
      {/* Summary header */}
      <div className="bg-gothic-dark/30 border border-amber-500/20 rounded-xl p-6 text-center">
        <p className="text-5xl font-gothic font-bold text-white text-glow">
          {army.totalModels}
        </p>
        <p className="text-gothic-light text-sm font-grim uppercase tracking-widest mt-1">
          Total Models
        </p>
        <p className="text-amber-400/80 text-sm font-grim mt-1">
          ~{totalPoints} pts estimated
        </p>
        <p className="text-gothic-light/40 text-xs font-grim mt-2">
          From {scanCount} {scanCount === 1 ? 'scan' : 'scans'} &middot; {sortedFactions.length} {sortedFactions.length === 1 ? 'faction' : 'factions'}
        </p>
      </div>

      {/* Faction breakdown */}
      <div className="space-y-2">
        {sortedFactions.map(f => {
          const factionPoints = getPointsPerModel(f.faction) * f.count
          const pct = (f.count / army.totalModels) * 100
          return (
            <div
              key={f.faction}
              className="flex items-center gap-3 px-4 py-3 rounded-xl border"
              style={{ borderColor: `${f.color}25` }}
            >
              <FactionIcon faction={f.faction} color={f.color} size={28} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-gothic text-white truncate">
                    {formatFactionName(f.faction)}
                  </span>
                  <span className="text-lg font-bold font-grim ml-2" style={{ color: f.color }}>
                    {f.count}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <div className="flex-1 h-1.5 bg-gothic-dark/40 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${pct}%`, backgroundColor: f.color, opacity: 0.7 }}
                    />
                  </div>
                  <span className="text-amber-400/60 text-[10px] font-grim w-14 text-right">
                    ~{factionPoints}pts
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <button
          onClick={handleClear}
          className={`flex-1 py-4 rounded-lg font-grim text-sm uppercase tracking-wider transition-all min-h-[48px] ${
            confirmClear
              ? 'bg-red-600 hover:bg-red-500 text-white'
              : 'bg-gothic-dark/60 border border-gothic-medium/40 text-gothic-light hover:bg-gothic-dark/80'
          }`}
        >
          {confirmClear ? 'Confirm Clear' : 'Clear Army'}
        </button>
        <button
          onClick={onScanMore}
          className="flex-1 py-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-grim text-sm uppercase tracking-wider shadow-glow-blue transition-all min-h-[48px]"
        >
          Scan More
        </button>
      </div>
    </div>
  )
}
