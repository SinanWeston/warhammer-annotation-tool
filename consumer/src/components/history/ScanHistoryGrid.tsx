import type { ScanResult } from '../../types/detection'
import HistoryCard from './HistoryCard'

interface ScanHistoryGridProps {
  scans: ScanResult[]
  onSelect: (scan: ScanResult) => void
  onDelete: (id: string) => void
}

export default function ScanHistoryGrid({ scans, onSelect, onDelete }: ScanHistoryGridProps) {
  if (scans.length === 0) return null

  return (
    <div>
      <h3 className="font-gothic text-lg text-gray-200 mb-3">Past Scans</h3>
      <div className="grid grid-cols-4 gap-4">
        {scans.map(scan => (
          <HistoryCard
            key={scan.id}
            scan={scan}
            onClick={() => onSelect(scan)}
            onDelete={() => onDelete(scan.id)}
          />
        ))}
      </div>
    </div>
  )
}
