import { useState, useEffect } from 'react'
import { getAllScans, clearAllScans, type StoredScan } from '../lib/db'
import { relativeTime } from '../utils/time'
import { formatFactionName } from '../utils/factionDisplay'
import FactionIcon from '../components/FactionIcon'

interface HistoryPageProps {
  onSelectScan: (scanId: string) => void
  onScanNew: () => void
}

export default function HistoryPage({ onSelectScan, onScanNew }: HistoryPageProps) {
  const [scans, setScans] = useState<StoredScan[]>([])
  const [loading, setLoading] = useState(true)
  const [confirmClear, setConfirmClear] = useState(false)

  useEffect(() => {
    getAllScans().then(s => {
      setScans(s)
      setLoading(false)
    })
  }, [])

  const handleClear = async () => {
    if (!confirmClear) {
      setConfirmClear(true)
      return
    }
    await clearAllScans()
    setScans([])
    setConfirmClear(false)
  }

  if (loading) {
    return (
      <div className="w-full flex items-center justify-center py-20">
        <p className="text-gothic-light/50 font-grim text-sm">Loading history...</p>
      </div>
    )
  }

  if (scans.length === 0) {
    return (
      <div className="w-full flex flex-col items-center gap-6 pt-12 animate-fade-in-down">
        <div className="w-16 h-16 rounded-full bg-gothic-dark/40 border border-gothic-medium/30 flex items-center justify-center">
          <svg className="w-8 h-8 text-gothic-light/30" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <circle cx="12" cy="12" r="10" />
            <path strokeLinecap="round" d="M12 6v6l4 2" />
          </svg>
        </div>
        <div className="text-center">
          <p className="text-white font-gothic text-lg">No scans yet</p>
          <p className="text-gothic-light/50 text-sm font-grim mt-1">Your scan history will appear here</p>
        </div>
        <button
          onClick={onScanNew}
          className="px-6 py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-grim text-sm uppercase tracking-wider shadow-glow-blue transition-all min-h-[48px]"
        >
          Start Scanning
        </button>
      </div>
    )
  }

  return (
    <div className="w-full flex flex-col gap-4 animate-fade-in-down pt-2">
      <div className="flex items-center justify-between">
        <h2 className="font-gothic text-lg text-white">
          Scan History
          <span className="text-gothic-light/40 text-sm ml-2 font-grim">{scans.length}</span>
        </h2>
        <button
          onClick={handleClear}
          className={`text-xs font-grim px-3 py-1.5 rounded-lg transition-colors min-h-[32px] ${
            confirmClear
              ? 'bg-red-600 hover:bg-red-500 text-white'
              : 'text-gothic-light/40 hover:text-red-400 hover:bg-white/5'
          }`}
        >
          {confirmClear ? 'Confirm Clear' : 'Clear All'}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {scans.map(scan => (
          <button
            key={scan.id}
            onClick={() => onSelectScan(scan.id)}
            className="text-left rounded-xl border border-gothic-medium/20 overflow-hidden hover:border-blue-400/30 transition-colors bg-gothic-dark/20"
          >
            {/* Thumbnail */}
            <div className="aspect-[4/3] overflow-hidden bg-gothic-dark/40">
              <img
                src={scan.imageDataUrl}
                alt="Scan"
                className="w-full h-full object-cover"
              />
            </div>
            {/* Info */}
            <div className="p-3">
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-white font-gothic text-sm">
                  {scan.results.totalDetected} <span className="text-gothic-light/50 text-xs font-grim">models</span>
                </span>
                <span className="text-gothic-light/40 text-[10px] font-grim">
                  {relativeTime(scan.timestamp)}
                </span>
              </div>
              <div className="flex flex-wrap gap-1">
                {scan.results.summary.slice(0, 3).map(s => (
                  <div
                    key={s.faction}
                    className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-grim"
                    style={{
                      backgroundColor: `${s.color}15`,
                      color: s.color,
                    }}
                  >
                    <FactionIcon faction={s.faction} color={s.color} size={12} />
                    {s.count}
                  </div>
                ))}
                {scan.results.summary.length > 3 && (
                  <span className="text-gothic-light/30 text-[10px] font-grim px-1">
                    +{scan.results.summary.length - 3}
                  </span>
                )}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
