import { useRef, useState, useCallback } from 'react'

interface PhotoUploadProps {
  onUpload: (blob: Blob, imageDataUrl: string) => void
}

export default function PhotoUpload({ onUpload }: PhotoUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)
  // 2.7 — Store File directly instead of roundtripping through fetch(dataUrl)
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFile = useCallback((f: File) => {
    if (!f.type.startsWith('image/')) return
    setFile(f)
    const reader = new FileReader()
    reader.onload = (e) => setPreview(e.target?.result as string)
    reader.readAsDataURL(f)
  }, [])

  const submitPreview = () => {
    if (!file || !preview) return
    onUpload(file, preview)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) handleFile(f)
  }

  const handleCancel = () => {
    setPreview(null)
    setFile(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  if (preview) {
    return (
      <div className="flex flex-col items-center gap-4">
        <div className="relative w-full aspect-[4/3] rounded-xl overflow-hidden border-2 border-gothic-dark/60">
          <img src={preview} alt="Selected photo" className="w-full h-full object-cover" />
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleCancel}
            className="px-5 py-3 rounded-lg bg-gothic-dark/60 border border-gothic-medium/40 text-gothic-light hover:text-white font-grim text-sm uppercase tracking-wider transition-colors min-h-[48px]"
          >
            Cancel
          </button>
          <button
            onClick={submitPreview}
            className="px-8 py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-grim text-sm uppercase tracking-wider shadow-glow-blue transition-all min-h-[48px]"
          >
            Scan
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`w-full border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all min-h-[120px] flex flex-col items-center justify-center gap-2 ${
        dragOver
          ? 'border-blue-400/60 bg-blue-400/5'
          : 'border-gothic-medium/30 hover:border-gothic-medium/50 hover:bg-gothic-dark/20'
      }`}
    >
      <svg className="w-8 h-8 text-gothic-light" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
      </svg>
      <p className="text-gothic-light text-sm">Upload a photo</p>
      <p className="text-gothic-light/50 text-xs">Drag & drop or tap to select</p>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleChange}
        className="hidden"
      />
    </div>
  )
}
