import type { ScanResult } from '../../types/detection'
import { relativeTime } from '../../utils/time'
import FactionIcon from '../FactionIcon'

interface HistoryCardProps {
  scan: ScanResult
  onClick: () => void
  onDelete: () => void
}

export default function HistoryCard({ scan, onClick, onDelete }: HistoryCardProps) {
  const factions = [...new Set(scan.detections.map(d => d.faction))]
  const totalPoints = scan.detections.reduce((sum, d) => sum + d.points, 0)

  return (
    <div
      onClick={onClick}
      className="bg-surface-2 border border-surface-3 rounded-lg overflow-hidden cursor-pointer hover:border-gothic-medium transition-colors group"
    >
      <div className="aspect-[4/3] bg-surface-1 relative">
        {scan.imageDataUrl && (
          <img src={scan.imageDataUrl} alt="Scan" className="w-full h-full object-cover" />
        )}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={e => { e.stopPropagation(); onDelete() }}
            className="w-6 h-6 bg-red-900/80 rounded text-red-200 text-xs hover:bg-red-800"
          >
            &times;
          </button>
        </div>
      </div>
      <div className="p-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gothic-light font-grim">{relativeTime(scan.timestamp)}</span>
          <span className="text-xs text-brass font-grim">{totalPoints} pts</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-300">{scan.detections.length} detections</span>
          <div className="flex gap-0.5 ml-auto">
            {factions.slice(0, 3).map(f => <FactionIcon key={f} faction={f} size="sm" />)}
            {factions.length > 3 && <span className="text-[10px] text-gothic-light">+{factions.length - 3}</span>}
          </div>
        </div>
      </div>
    </div>
  )
}
