import { useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useScanStore } from '../stores/scanStore'
import { useArmyStore } from '../stores/armyStore'
import { useBboxInteraction } from '../hooks/useBboxInteraction'
import { getScan } from '../services/storageService'
import SplitView from '../components/results/SplitView'
import BboxCanvas from '../components/results/BboxCanvas'
import UnitList from '../components/results/UnitList'
import EmptyState from '../components/EmptyState'

export default function ResultsPage() {
  const { scanId } = useParams()
  const navigate = useNavigate()
  const result = useScanStore(s => s.currentResult)
  const setCurrentResult = useScanStore(s => s.setCurrentResult)
  const groupingMode = useScanStore(s => s.groupingMode)
  const setGroupingMode = useScanStore(s => s.setGroupingMode)
  const addUnitsFromDetections = useArmyStore(s => s.addUnitsFromDetections)

  const {
    highlightedId, selectedId,
    onCanvasHover, onCanvasClick,
    onCardHover, onCardClick,
    registerCardRef,
  } = useBboxInteraction()

  // Load scan from IndexedDB if navigating directly to /results/:scanId
  useEffect(() => {
    if (scanId && (!result || result.id !== scanId)) {
      getScan(scanId).then(scan => {
        if (scan) setCurrentResult(scan)
      })
    }
  }, [scanId, result, setCurrentResult])

  if (!result) {
    return (
      <EmptyState
        icon="?"
        title="No Scan Results"
        message="Upload photos and scan your army first to see detection results here."
        action={{ label: 'Go to Scan', onClick: () => navigate('/scan') }}
      />
    )
  }

  const handleAddToArmy = () => {
    addUnitsFromDetections(result.detections, result.id)
    navigate('/army')
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-gothic text-2xl text-brass-light">Scan Results</h2>
        <button
          onClick={handleAddToArmy}
          className="px-4 py-2 bg-brass text-gothic-darker rounded font-grim text-sm hover:bg-brass-light transition-colors"
        >
          Add to Army Builder
        </button>
      </div>

      <SplitView
        left={
          <BboxCanvas
            imageDataUrl={result.imageDataUrl}
            imageWidth={result.imageWidth}
            imageHeight={result.imageHeight}
            detections={result.detections}
            highlightedId={highlightedId}
            selectedId={selectedId}
            onHover={onCanvasHover}
            onClick={onCanvasClick}
          />
        }
        right={
          <UnitList
            detections={result.detections}
            groupingMode={groupingMode}
            onGroupingChange={setGroupingMode}
            highlightedId={highlightedId}
            selectedId={selectedId}
            onHover={onCardHover}
            onClick={onCardClick}
            registerRef={registerCardRef}
          />
        }
      />
    </div>
  )
}
