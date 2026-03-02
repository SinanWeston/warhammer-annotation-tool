import { useState, useEffect, useRef, useCallback } from 'react'
import { getStats, clearSyncedImages } from '../lib/db'
import { importZip } from '../lib/zip'
import { onOnlineStatusChange } from '../lib/sync'
import SyncStatus from '../components/SyncStatus'

interface Props {
  onStartAnnotating: () => void
}

export default function HomePage({ onStartAnnotating }: Props) {
  const [stats, setStats] = useState({ totalImages: 0, annotated: 0, pendingSync: 0 })
  const [importing, setImporting] = useState(false)
  const [importProgress, setImportProgress] = useState({ loaded: 0, total: 0 })
  const [storageUsage, setStorageUsage] = useState<{ used: number; quota: number } | null>(null)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [online, setOnline] = useState(navigator.onLine)
  const fileRef = useRef<HTMLInputElement>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout>>(0 as any)

  const showToast = useCallback((message: string, type: 'success' | 'error' = 'success') => {
    clearTimeout(toastTimer.current)
    setToast({ message, type })
    toastTimer.current = setTimeout(() => setToast(null), 3000)
  }, [])

  const refreshStats = useCallback(async () => {
    setStats(await getStats())
    if (navigator.storage?.estimate) {
      const est = await navigator.storage.estimate()
      setStorageUsage({ used: est.usage || 0, quota: est.quota || 0 })
    }
  }, [])

  useEffect(() => { refreshStats() }, [refreshStats])

  // Reactive online/offline
  useEffect(() => onOnlineStatusChange(setOnline), [])

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setImporting(true)
    setImportProgress({ loaded: 0, total: 0 })
    try {
      const count = await importZip(file, (loaded, total) => {
        setImportProgress({ loaded, total })
      })
      showToast(`Imported ${count} images`, 'success')
      await refreshStats()
    } catch (err) {
      showToast(`Import failed: ${err instanceof Error ? err.message : 'Unknown error'}`, 'error')
    } finally {
      setImporting(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleClearSynced = async () => {
    if (!confirm('Delete all synced images from this device? This cannot be undone.')) return
    const cleared = await clearSyncedImages()
    showToast(`Cleared ${cleared} synced images`, 'success')
    await refreshStats()
  }

  const formatBytes = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const storagePercent = storageUsage
    ? Math.round((storageUsage.used / storageUsage.quota) * 100)
    : 0

  return (
    <div className="flex-1 flex flex-col p-4 safe-top safe-bottom">
      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-4 left-4 right-4 z-50 px-4 py-3 rounded-lg text-sm font-grim text-center shadow-lg transition-all ${
            toast.type === 'success'
              ? 'bg-green-600/90 text-white'
              : 'bg-red-600/90 text-white'
          }`}
        >
          {toast.message}
        </div>
      )}

      {/* Header */}
      <div className="text-center mb-6 pt-2">
        <h1 className="font-gothic text-2xl font-bold text-glow">40K ANNOTATOR</h1>
        <p className="font-grim text-xs text-gothic-light mt-1 tracking-widest">OFFLINE MOBILE</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-gothic-dark/40 rounded-lg p-3 text-center border border-gothic-medium/30">
          <div className="font-grim text-2xl text-blue-400">{stats.totalImages}</div>
          <div className="text-xs text-gothic-light mt-1">Stored</div>
        </div>
        <div className="bg-gothic-dark/40 rounded-lg p-3 text-center border border-gothic-medium/30">
          <div className="font-grim text-2xl text-green-400">{stats.annotated}</div>
          <div className="text-xs text-gothic-light mt-1">Annotated</div>
        </div>
        <div className="bg-gothic-dark/40 rounded-lg p-3 text-center border border-gothic-medium/30">
          <div className="font-grim text-2xl text-amber-400">{stats.pendingSync}</div>
          <div className="text-xs text-gothic-light mt-1">Pending Sync</div>
        </div>
      </div>

      {/* Storage Bar */}
      {storageUsage && (
        <div className="mb-6">
          <div className="flex justify-between text-xs text-gothic-light mb-1">
            <span>Storage</span>
            <span>{formatBytes(storageUsage.used)} / {formatBytes(storageUsage.quota)}</span>
          </div>
          <div className="h-2 bg-gothic-dark/60 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                storagePercent > 80 ? 'bg-red-500' : storagePercent > 50 ? 'bg-amber-500' : 'bg-blue-500'
              }`}
              style={{ width: `${Math.min(storagePercent, 100)}%` }}
            />
          </div>
          {storagePercent > 80 && (
            <p className="text-xs text-red-400 mt-1">Storage nearly full. Clear synced images to free space.</p>
          )}
        </div>
      )}

      {/* Import */}
      <input
        ref={fileRef}
        type="file"
        accept=".zip"
        onChange={handleImport}
        className="hidden"
      />
      <button
        onClick={() => fileRef.current?.click()}
        disabled={importing}
        className="w-full py-3 rounded-lg bg-gothic-dark border border-gothic-medium/50 text-gray-200 font-grim text-sm tracking-wider active:scale-[0.98] transition-all disabled:opacity-50 mb-3"
      >
        {importing
          ? `Importing... ${importProgress.loaded}/${importProgress.total}`
          : 'IMPORT PHOTOS (.zip)'}
      </button>

      {importing && importProgress.total > 0 && (
        <div className="h-1.5 bg-gothic-dark/60 rounded-full overflow-hidden mb-3">
          <div
            className="h-full bg-blue-500 rounded-full transition-all"
            style={{ width: `${(importProgress.loaded / importProgress.total) * 100}%` }}
          />
        </div>
      )}

      {/* Start Annotating */}
      <button
        onClick={onStartAnnotating}
        disabled={stats.totalImages === 0 || stats.totalImages === stats.annotated}
        className="w-full py-4 rounded-lg bg-blue-600 text-white font-gothic text-lg font-bold tracking-wider shadow-glow-md active:scale-[0.98] transition-all disabled:opacity-30 disabled:shadow-none mb-3"
      >
        START ANNOTATING
      </button>

      {stats.totalImages > 0 && stats.totalImages === stats.annotated && (
        <p className="text-center text-sm text-green-400 mb-3">All images annotated!</p>
      )}

      {/* Sync */}
      <SyncStatus onSyncComplete={refreshStats} />

      {/* Clear Synced */}
      {stats.pendingSync === 0 && stats.annotated > 0 && (
        <button
          onClick={handleClearSynced}
          className="w-full py-2 rounded-lg border border-red-500/30 text-red-400 text-sm mt-3 active:scale-[0.98] transition-all"
        >
          Clear Synced Images
        </button>
      )}

      {/* Offline Banner */}
      {!online && (
        <div className="mt-auto pt-4">
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 text-center">
            <p className="text-amber-400 text-sm font-grim">OFFLINE MODE</p>
            <p className="text-xs text-gothic-light mt-1">Annotations saved locally</p>
          </div>
        </div>
      )}
    </div>
  )
}
