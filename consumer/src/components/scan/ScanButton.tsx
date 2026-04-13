import { useNavigate } from 'react-router-dom'
import { useScanStore } from '../../stores/scanStore'
import Spinner from '../Spinner'

export default function ScanButton() {
  const hasImages = useScanStore(s => s.uploadedImages.length > 0)
  const isScanning = useScanStore(s => s.isScanning)
  const scanError = useScanStore(s => s.scanError)
  const startScan = useScanStore(s => s.startScan)
  const navigate = useNavigate()

  const handleScan = async () => {
    const result = await startScan()
    if (result) {
      navigate(`/results/${result.id}`)
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        onClick={handleScan}
        disabled={!hasImages || isScanning}
        className="px-6 py-3 bg-brass text-gothic-darker rounded font-gothic font-bold text-lg
                   hover:bg-brass-light disabled:opacity-40 disabled:cursor-not-allowed
                   transition-colors flex items-center gap-3"
      >
        {isScanning ? (
          <>
            <Spinner size="sm" />
            <span>Scanning...</span>
          </>
        ) : (
          'Scan Army'
        )}
      </button>
      {scanError && (
        <p className="text-sm text-red-400">{scanError}</p>
      )}
    </div>
  )
}
