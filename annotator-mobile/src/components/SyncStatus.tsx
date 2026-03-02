import { useState, useEffect, useRef } from 'react'
import { syncAnnotations, getOnlineStatus, onOnlineStatusChange } from '../lib/sync'
import { getStats, getPendingSync, markSynced } from '../lib/db'

interface Props {
  onSyncComplete?: () => void
}

export default function SyncStatus({ onSyncComplete }: Props) {
  const [online, setOnline] = useState(getOnlineStatus())
  const [pendingCount, setPendingCount] = useState(0)
  const [syncing, setSyncing] = useState(false)
  const [lastSync, setLastSync] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [backendUrl, setBackendUrl] = useState(() => localStorage.getItem('backendUrl') || '')
  const [editingUrl, setEditingUrl] = useState(false)
  const urlInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const unsub = onOnlineStatusChange(setOnline)
    return unsub
  }, [])

  useEffect(() => {
    getStats().then(s => setPendingCount(s.pendingSync))
  }, [])

  const [exported, setExported] = useState(false)
  const [exportedIds, setExportedIds] = useState<string[]>([])

  const handleSync = async () => {
    setSyncing(true)
    setError(null)
    try {
      const result = await syncAnnotations()
      setLastSync(new Date().toLocaleTimeString())
      setPendingCount(prev => Math.max(0, prev - result.synced))
      if (result.errors.length > 0) {
        setError(`${result.errors.length} errors — use Export File instead`)
      }
      onSyncComplete?.()
    } catch (err) {
      setError('Direct sync failed — use Export File instead')
    } finally {
      setSyncing(false)
    }
  }

  const handleExport = async () => {
    const pending = await getPendingSync()
    if (pending.length === 0) return
    const payload = JSON.stringify({ annotations: pending }, null, 2)
    const file = new File([payload], `annotations-${new Date().toISOString().split('T')[0]}.json`, { type: 'application/json' })
    // Try Web Share API first (iOS share sheet → pCloud, AirDrop, etc.)
    if (navigator.canShare?.({ files: [file] })) {
      try {
        await navigator.share({ files: [file], title: 'Annotations Export' })
        setExportedIds(pending.map(a => a.imageId))
        setExported(true)
        return
      } catch { /* user cancelled — fall through to download */ }
    }
    // Fallback: trigger file download
    const url = URL.createObjectURL(file)
    const a = document.createElement('a')
    a.href = url
    a.download = file.name
    a.click()
    URL.revokeObjectURL(url)
    setExportedIds(pending.map(a => a.imageId))
    setExported(true)
  }

  const handleMarkSynced = async () => {
    await markSynced(exportedIds)
    setPendingCount(0)
    setExported(false)
    setExportedIds([])
    setLastSync(new Date().toLocaleTimeString())
    onSyncComplete?.()
  }

  return (
    <div className="bg-gothic-dark/30 border border-gothic-medium/30 rounded-lg p-3 mt-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${online ? 'bg-green-400' : 'bg-red-400'}`} />
          <span className="text-xs text-gothic-light font-grim">
            {online ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
        {lastSync && (
          <span className="text-xs text-gothic-light">Last: {lastSync}</span>
        )}
      </div>

      {pendingCount > 0 && (
        <p className="text-xs text-amber-400 font-grim mb-2">
          {pendingCount} annotation{pendingCount !== 1 ? 's' : ''} pending sync
        </p>
      )}

      {error && (
        <p className="text-xs text-red-400 mb-2">{error}</p>
      )}

      {/* Export file — works from anywhere */}
      <button
        onClick={handleExport}
        disabled={pendingCount === 0}
        className="w-full py-2 rounded-lg bg-blue-700 border border-blue-500/50 text-sm font-grim tracking-wider disabled:opacity-30 active:scale-[0.98] transition-all"
      >
        EXPORT TO FILE ({pendingCount})
      </button>

      {exported && (
        <div className="mt-2 p-2 bg-green-900/30 border border-green-500/30 rounded-lg">
          <p className="text-xs text-green-300 font-grim mb-1.5">
            File exported! Save it to pCloud, then on your PC run:
          </p>
          <code className="text-xs text-green-200 font-mono block bg-black/30 px-2 py-1 rounded">
            npm run sync:mobile
          </code>
          <button
            onClick={handleMarkSynced}
            className="mt-2 w-full py-1.5 rounded bg-green-700/50 text-xs text-green-200 font-grim active:scale-[0.98] transition-all"
          >
            ✓ IMPORTED ON PC — MARK AS SYNCED
          </button>
        </div>
      )}

      {/* Direct sync (only works on local network HTTP) */}
      <button
        onClick={handleSync}
        disabled={!online || syncing || pendingCount === 0}
        className="w-full py-1.5 mt-1 rounded-lg bg-gothic-dark border border-gothic-medium/30 text-xs font-grim tracking-wider disabled:opacity-30 active:scale-[0.98] transition-all flex items-center justify-center gap-2 text-gothic-light/50"
      >
        {syncing && <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
        {syncing ? 'SYNCING...' : 'DIRECT SYNC (local network only)'}
      </button>
    </div>
  )
}
