import { DetectionResult } from '../types/detection'
import FactionIcon from './FactionIcon'
import { formatFactionName } from '../utils/factionDisplay'
import { estimateTotalPoints } from '../utils/points'

interface ArmySummaryProps {
  results: DetectionResult
}

export default function ArmySummary({ results }: ArmySummaryProps) {
  if (results.totalDetected === 0) return null

  return (
    <div className="bg-gothic-dark/30 border border-gothic-medium/30 rounded-xl p-6">
      {/* Total count */}
      <div className="text-center mb-4">
        <p className="text-5xl font-gothic font-bold text-white text-glow">
          {results.totalDetected}
        </p>
        <p className="text-gothic-light text-sm font-grim uppercase tracking-widest mt-1">
          Miniatures Detected
        </p>
        <p className="text-amber-400/80 text-sm font-grim mt-1">
          ~{estimateTotalPoints(results)} pts estimated
        </p>
      </div>

      {/* Faction count */}
      <p className="text-center text-gothic-light/60 text-xs font-grim mb-4">
        {results.summary.length} {results.summary.length === 1 ? 'faction' : 'factions'} identified
      </p>

      {/* 1.4 + 3.1 — Formatted faction names with FactionIcon badges */}
      <div className="flex flex-wrap justify-center gap-2">
        {results.summary.map((faction) => (
          <div
            key={faction.faction}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full border"
            style={{
              borderColor: `${faction.color}40`,
              backgroundColor: `${faction.color}10`,
            }}
          >
            <FactionIcon faction={faction.faction} color={faction.color} size={18} />
            <span className="text-xs font-grim text-gray-200">
              {formatFactionName(faction.faction)}
            </span>
            <span
              className="text-xs font-bold"
              style={{ color: faction.color }}
            >
              {faction.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
