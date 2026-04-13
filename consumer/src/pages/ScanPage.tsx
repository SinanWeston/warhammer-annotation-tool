import PhotoUploader from '../components/scan/PhotoUploader'
import ImagePreviewGrid from '../components/scan/ImagePreviewGrid'
import ImageCropper from '../components/scan/ImageCropper'
import FactionHintSelector from '../components/scan/FactionHintSelector'
import ScanButton from '../components/scan/ScanButton'
import { useScanStore } from '../stores/scanStore'
import { useUiStore } from '../stores/uiStore'

export default function ScanPage() {
  const imageCount = useScanStore(s => s.uploadedImages.length)
  const clearUpload = useScanStore(s => s.clearUpload)
  const cropImageId = useUiStore(s => s.cropImageId)

  return (
    <div className="max-w-3xl">
      <h2 className="font-gothic text-2xl text-brass-light mb-1">Scan Your Army</h2>
      <p className="text-sm text-gothic-light mb-6">
        Upload photos of your Warhammer 40K miniatures. The scanner will identify units, count models, and calculate points.
      </p>

      <PhotoUploader />
      <ImagePreviewGrid />

      {imageCount > 0 && (
        <div className="mt-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <FactionHintSelector />
            <span className="text-xs text-gothic-light">
              {imageCount} photo{imageCount !== 1 ? 's' : ''} ready
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={clearUpload}
              className="px-4 py-2 text-sm text-gothic-light hover:text-gray-300 font-grim"
            >
              Clear All
            </button>
            <ScanButton />
          </div>
        </div>
      )}

      {cropImageId && <ImageCropper />}
    </div>
  )
}
