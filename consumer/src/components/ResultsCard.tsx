import { useState } from 'react'
import { FactionSummary, Detection } from '../types/detection'
import FactionIcon from './FactionIcon'
import { formatFactionName } from '../utils/factionDisplay'
import { estimateFactionPoints } from '../utils/points'

interface ResultsCardProps {
  faction: FactionSummary
  detections: Detection[]
  onReportWrong?: (detectionIndex: number, faction: string) => void
}

export default function ResultsCard({ faction, detections, onReportWrong }: ResultsCardProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className="border rounded-xl overflow-hidden"
      style={{ borderColor: `${faction.color}30` }}
    >
      {/* Card header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-white/5 transition-colors min-h-[48px]"
      >
        <div className="flex items-center gap-3">
          {/* 1.4 + 3.1 — Formatted name with FactionIcon */}
          <FactionIcon faction={faction.faction} color={faction.color} size={22} />
          <h3 className="font-gothic text-lg text-white">
            {formatFactionName(faction.faction)}
          </h3>
        </div>
        <div className="flex items-center gap-4">
          <span
            className="text-2xl font-bold font-grim"
            style={{ color: faction.color }}
          >
            {faction.count}
          </span>
          <span className="text-amber-400/70 text-xs font-grim">
            ~{estimateFactionPoints(faction.faction, faction.count)}pts
          </span>
          <span className="text-gothic-light/50 text-xs font-grim">
            {(faction.avgConfidence * 100).toFixed(0)}%
          </span>
          <svg
            className={`w-4 h-4 text-gothic-light transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t px-4 py-3 space-y-2" style={{ borderColor: `${faction.color}20` }}>
          {detections.map((det, i) => (
            <div key={i} className="flex items-center gap-3">
              <span className="text-gothic-light/50 text-xs font-grim w-6">#{i + 1}</span>
              <div className="flex-1 h-2 bg-gothic-dark/40 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${det.confidence * 100}%`,
                    backgroundColor: faction.color,
                    opacity: 0.7 + det.confidence * 0.3,
                  }}
                />
              </div>
              <span className="text-xs font-grim text-gothic-light/70 w-12 text-right">
                {(det.confidence * 100).toFixed(1)}%
              </span>
              {onReportWrong && (
                <button
                  onClick={(e) => { e.stopPropagation(); onReportWrong(i, faction.faction) }}
                  className="w-6 h-6 flex items-center justify-center rounded text-gothic-light/30 hover:text-amber-400 hover:bg-amber-400/10 transition-colors shrink-0"
                  title="Report wrong detection"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1-1H5a2 2 0 00-2 2z" />
                  </svg>
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
