import { useState, useCallback } from 'react'
import Cropper from 'react-easy-crop'
import type { Area, Point } from 'react-easy-crop'
import { useScanStore } from '../../stores/scanStore'
import { useUiStore } from '../../stores/uiStore'
import { cropImage } from '../../utils/cropImage'

export default function ImageCropper() {
  const cropImageId = useUiStore(s => s.cropImageId)
  const setCropImageId = useUiStore(s => s.setCropImageId)
  const images = useScanStore(s => s.uploadedImages)
  const setCroppedImage = useScanStore(s => s.setCroppedImage)

  const [crop, setCrop] = useState<Point>({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [croppedArea, setCroppedArea] = useState<Area | null>(null)

  const image = images.find(i => i.id === cropImageId)

  const onCropComplete = useCallback((_: Area, croppedAreaPixels: Area) => {
    setCroppedArea(croppedAreaPixels)
  }, [])

  const handleSave = useCallback(async () => {
    if (!croppedArea || !image) return
    const src = image.previewUrl
    const { blob, url } = await cropImage(src, croppedArea)
    setCroppedImage(image.id, blob, url)
    setCropImageId(null)
    setCrop({ x: 0, y: 0 })
    setZoom(1)
  }, [croppedArea, image, setCroppedImage, setCropImageId])

  const handleCancel = useCallback(() => {
    setCropImageId(null)
    setCrop({ x: 0, y: 0 })
    setZoom(1)
  }, [setCropImageId])

  if (!image) return null

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center">
      <div className="bg-surface-1 rounded-lg w-[700px] h-[550px] flex flex-col">
        <div className="px-4 py-3 border-b border-surface-3 flex items-center justify-between">
          <h3 className="font-gothic text-brass-light">Crop Image</h3>
          <button onClick={handleCancel} className="text-gothic-light hover:text-gray-300 text-lg">&times;</button>
        </div>

        <div className="flex-1 relative">
          <Cropper
            image={image.previewUrl}
            crop={crop}
            zoom={zoom}
            aspect={4 / 3}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={onCropComplete}
          />
        </div>

        <div className="px-4 py-3 border-t border-surface-3 flex items-center justify-between">
          <label className="flex items-center gap-3 text-sm text-gothic-light">
            Zoom
            <input
              type="range"
              min={1}
              max={3}
              step={0.1}
              value={zoom}
              onChange={e => setZoom(Number(e.target.value))}
              className="w-32"
            />
          </label>
          <div className="flex gap-2">
            <button
              onClick={handleCancel}
              className="px-4 py-2 bg-surface-3 text-gray-300 rounded font-grim text-sm hover:bg-surface-4"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-2 bg-brass text-gothic-darker rounded font-grim text-sm hover:bg-brass-light"
            >
              Apply Crop
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
