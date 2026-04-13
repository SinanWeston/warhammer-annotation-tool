import { useScanStore } from '../../stores/scanStore'
import { useUiStore } from '../../stores/uiStore'

export default function ImagePreviewGrid() {
  const images = useScanStore(s => s.uploadedImages)
  const removeImage = useScanStore(s => s.removeImage)
  const setCropImageId = useUiStore(s => s.setCropImageId)

  if (images.length === 0) return null

  return (
    <div className="grid grid-cols-4 gap-3 mt-4">
      {images.map(img => (
        <div key={img.id} className="relative group rounded overflow-hidden bg-surface-2 aspect-[4/3]">
          <img
            src={img.croppedUrl || img.previewUrl}
            alt="Uploaded"
            className="w-full h-full object-cover"
          />
          {/* Overlay controls */}
          <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
            <button
              onClick={(e) => { e.stopPropagation(); setCropImageId(img.id) }}
              className="px-3 py-1.5 bg-surface-3 text-gray-200 text-xs rounded font-grim hover:bg-gothic-medium"
            >
              Crop
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); removeImage(img.id) }}
              className="px-3 py-1.5 bg-red-900/80 text-red-200 text-xs rounded font-grim hover:bg-red-800"
            >
              Remove
            </button>
          </div>
          {img.croppedUrl && (
            <div className="absolute top-1 right-1 bg-brass/80 text-gothic-darker text-[10px] px-1.5 py-0.5 rounded font-grim">
              Cropped
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
