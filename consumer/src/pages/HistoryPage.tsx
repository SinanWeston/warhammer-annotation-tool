import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useHistoryStore } from '../stores/historyStore'
import { useScanStore } from '../stores/scanStore'
import { useArmyStore } from '../stores/armyStore'
import ScanHistoryGrid from '../components/history/ScanHistoryGrid'
import SavedArmyList from '../components/history/SavedArmyList'
import EmptyState from '../components/EmptyState'
import Spinner from '../components/Spinner'
import type { ScanResult } from '../types/detection'
import type { Army } from '../types/army'

export default function HistoryPage() {
  const navigate = useNavigate()
  const { scans, armies, isLoading, loadHistory, removeScan, removeArmy } = useHistoryStore()
  const setCurrentResult = useScanStore(s => s.setCurrentResult)
  const loadArmy = useArmyStore(s => s.loadArmy)

  useEffect(() => {
    loadHistory()
  }, [loadHistory])

  const handleSelectScan = (scan: ScanResult) => {
    setCurrentResult(scan)
    navigate(`/results/${scan.id}`)
  }

  const handleSelectArmy = (army: Army) => {
    loadArmy(army)
    navigate('/army')
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Spinner />
      </div>
    )
  }

  if (scans.length === 0 && armies.length === 0) {
    return (
      <EmptyState
        icon="?"
        title="No History Yet"
        message="Your scan results and saved armies will appear here."
        action={{ label: 'Start Scanning', onClick: () => navigate('/scan') }}
      />
    )
  }

  return (
    <div>
      <h2 className="font-gothic text-2xl text-brass-light mb-6">History</h2>
      <ScanHistoryGrid
        scans={scans}
        onSelect={handleSelectScan}
        onDelete={removeScan}
      />
      <SavedArmyList
        armies={armies}
        onSelect={handleSelectArmy}
        onDelete={removeArmy}
      />
    </div>
  )
}
