import { useCallback, useRef } from 'react'
import { useScanStore } from '../../stores/scanStore'

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20MB

export default function PhotoUploader() {
  const addImages = useScanStore(s => s.addImages)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files) return
      const valid: File[] = []
      for (const file of Array.from(files)) {
        if (!ACCEPTED_TYPES.includes(file.type)) continue
        if (file.size > MAX_FILE_SIZE) continue
        valid.push(file)
      }
      if (valid.length > 0) addImages(valid)
    },
    [addImages]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles]
  )

  return (
    <div
      onDrop={handleDrop}
      onDragOver={e => e.preventDefault()}
      onClick={() => inputRef.current?.click()}
      className="border-2 border-dashed border-gothic-medium rounded-lg p-8 text-center cursor-pointer
                 hover:border-brass transition-colors bg-surface-1"
    >
      <div className="text-3xl text-gothic-light mb-3">+</div>
      <p className="text-sm text-gray-300 font-grim">
        Drop photos here or click to browse
      </p>
      <p className="text-xs text-gothic-light mt-2">
        JPG, PNG, or WebP — up to 20 MB each
      </p>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        className="hidden"
        onChange={e => handleFiles(e.target.files)}
      />
    </div>
  )
}
