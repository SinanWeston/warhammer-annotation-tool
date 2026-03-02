import { useState, useEffect, useCallback } from 'react'
import Header from './components/Header'
import HealthBanner from './components/HealthBanner'
import ScanPage from './pages/ScanPage'
import ResultsPage from './pages/ResultsPage'
import HistoryPage from './pages/HistoryPage'
import ArmyPage from './pages/ArmyPage'
import OnboardingModal from './components/OnboardingModal'
import { DetectionResult, AccumulatedArmy } from './types/detection'
import { saveScan, getScan, type StoredScan } from './lib/db'

type Page = 'scan' | 'results' | 'history' | 'army'

function buildAccumulatedArmy(scans: StoredScan[]): AccumulatedArmy {
  const factionCounts: Record<string, { count: number; color: string }> = {}

  for (const scan of scans) {
    for (const s of scan.results.summary) {
      if (!factionCounts[s.faction]) {
        factionCounts[s.faction] = { count: 0, color: s.color }
      }
      factionCounts[s.faction].count += s.count
    }
  }

  return {
    scanIds: scans.map(s => s.id),
    factions: Object.entries(factionCounts).map(([faction, { count, color }]) => ({
      faction,
      count,
      color,
    })),
    totalModels: Object.values(factionCounts).reduce((sum, f) => sum + f.count, 0),
  }
}

export default function App() {
  const [page, setPage] = useState<Page>('scan')
  const [results, setResults] = useState<DetectionResult | null>(null)
  const [scannedImage, setScannedImage] = useState<string | null>(null)
  const [currentScanId, setCurrentScanId] = useState<string | null>(null)

  // Onboarding
  const [showOnboarding, setShowOnboarding] = useState(
    () => !localStorage.getItem('battle-scanner-onboarded')
  )

  // Army accumulation
  const [accumulatedScans, setAccumulatedScans] = useState<StoredScan[]>([])

  // PWA install prompt
  const [installPrompt, setInstallPrompt] = useState<any>(null)
  const [showInstallBanner, setShowInstallBanner] = useState(false)

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault()
      setInstallPrompt(e)
    }
    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [])

  const handleDetection = useCallback(async (result: DetectionResult, imageDataUrl: string) => {
    setResults(result)
    setScannedImage(imageDataUrl)
    setPage('results')
    if (installPrompt) setShowInstallBanner(true)

    // Persist to IndexedDB
    const stored = await saveScan(imageDataUrl, result)
    setCurrentScanId(stored.id)
  }, [installPrompt])

  const handleScanAnother = useCallback(() => {
    setResults(null)
    setScannedImage(null)
    setCurrentScanId(null)
    setPage('scan')
  }, [])

  const handleViewHistory = useCallback(() => {
    setPage('history')
  }, [])

  const handleSelectScan = useCallback(async (scanId: string) => {
    const scan = await getScan(scanId)
    if (scan) {
      setResults(scan.results)
      setScannedImage(scan.imageDataUrl)
      setCurrentScanId(scan.id)
      setPage('results')
    }
  }, [])

  const handleAddToArmy = useCallback(async () => {
    if (!currentScanId) return
    const scan = await getScan(currentScanId)
    if (!scan) return
    // Avoid duplicates
    setAccumulatedScans(prev => {
      if (prev.some(s => s.id === scan.id)) return prev
      return [...prev, scan]
    })
    setPage('army')
  }, [currentScanId])

  const handleClearArmy = useCallback(() => {
    setAccumulatedScans([])
  }, [])

  const handleArmyClick = useCallback(() => {
    setPage('army')
  }, [])

  const handleInfoClick = useCallback(() => {
    setShowOnboarding(true)
  }, [])

  const handleDismissOnboarding = useCallback(() => {
    setShowOnboarding(false)
    localStorage.setItem('battle-scanner-onboarded', '1')
  }, [])

  const handleInstall = async () => {
    if (!installPrompt) return
    installPrompt.prompt()
    const { outcome } = await installPrompt.userChoice
    if (outcome === 'accepted') setInstallPrompt(null)
    setShowInstallBanner(false)
  }

  const army = accumulatedScans.length > 0 ? buildAccumulatedArmy(accumulatedScans) : null

  return (
    <div className="flex flex-col min-h-[100dvh]">
      <Header
        currentPage={page}
        onInfoClick={handleInfoClick}
        onHistoryClick={handleViewHistory}
        onArmyClick={handleArmyClick}
        armyScanCount={accumulatedScans.length}
      />
      <HealthBanner />

      {/* Onboarding modal */}
      {showOnboarding && <OnboardingModal onDismiss={handleDismissOnboarding} />}

      {/* PWA install banner */}
      {showInstallBanner && installPrompt && (
        <div className="mx-4 mb-2 flex items-center justify-between gap-3 bg-blue-900/40 border border-blue-500/30 rounded-lg px-4 py-3">
          <p className="text-blue-200 text-xs font-grim">Add Battle Scanner to your home screen</p>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => setShowInstallBanner(false)}
              className="text-blue-400/60 hover:text-blue-400 text-xs font-grim transition-colors"
            >
              Later
            </button>
            <button
              onClick={handleInstall}
              className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs font-grim rounded transition-colors min-h-[32px]"
            >
              Install
            </button>
          </div>
        </div>
      )}

      <main className="flex-1 flex flex-col items-center w-full max-w-2xl mx-auto px-4 pb-8">
        {page === 'scan' && <ScanPage onDetection={handleDetection} />}
        {page === 'results' && results && scannedImage && (
          <ResultsPage
            results={results}
            scannedImage={scannedImage}
            scanId={currentScanId}
            onScanAnother={handleScanAnother}
            onAddToArmy={handleAddToArmy}
          />
        )}
        {page === 'history' && (
          <HistoryPage
            onSelectScan={handleSelectScan}
            onScanNew={handleScanAnother}
          />
        )}
        {page === 'army' && (
          <ArmyPage
            army={army}
            scanCount={accumulatedScans.length}
            onClearArmy={handleClearArmy}
            onScanMore={handleScanAnother}
          />
        )}
      </main>
    </div>
  )
}
