import { create } from 'zustand'
import type { ScanResult, Detection, GroupingMode } from '../types/detection'
import { detectFromImages } from '../services/detectionService'
import { saveScan } from '../services/storageService'

interface UploadedImage {
  id: string
  file: File
  previewUrl: string
  croppedBlob?: Blob
  croppedUrl?: string
}

interface ScanState {
  // Upload
  uploadedImages: UploadedImage[]
  factionHint: string | undefined
  addImages: (files: File[]) => void
  removeImage: (id: string) => void
  setCroppedImage: (id: string, blob: Blob, url: string) => void
  setFactionHint: (hint: string | undefined) => void
  clearUpload: () => void

  // Scanning
  isScanning: boolean
  scanError: string | null
  startScan: () => Promise<ScanResult | null>

  // Results
  currentResult: ScanResult | null
  setCurrentResult: (result: ScanResult | null) => void
  highlightedDetectionId: string | null
  selectedDetectionId: string | null
  setHighlightedDetection: (id: string | null) => void
  setSelectedDetection: (id: string | null) => void
  groupingMode: GroupingMode
  setGroupingMode: (mode: GroupingMode) => void

  // Editing
  editDetection: (id: string, updates: Partial<Pick<Detection, 'unitName' | 'points' | 'faction' | 'role'>>) => void
  removeDetection: (id: string) => void
}

let nextImageId = 0

export const useScanStore = create<ScanState>((set, get) => ({
  // Upload
  uploadedImages: [],
  factionHint: undefined,

  addImages: (files) => {
    const newImages: UploadedImage[] = files.map(file => ({
      id: `img-${++nextImageId}`,
      file,
      previewUrl: URL.createObjectURL(file),
    }))
    set(s => ({ uploadedImages: [...s.uploadedImages, ...newImages] }))
  },

  removeImage: (id) => {
    set(s => {
      const img = s.uploadedImages.find(i => i.id === id)
      if (img) {
        URL.revokeObjectURL(img.previewUrl)
        if (img.croppedUrl) URL.revokeObjectURL(img.croppedUrl)
      }
      return { uploadedImages: s.uploadedImages.filter(i => i.id !== id) }
    })
  },

  setCroppedImage: (id, blob, url) => {
    set(s => ({
      uploadedImages: s.uploadedImages.map(img =>
        img.id === id ? { ...img, croppedBlob: blob, croppedUrl: url } : img
      ),
    }))
  },

  setFactionHint: (hint) => set({ factionHint: hint }),

  clearUpload: () => {
    const { uploadedImages } = get()
    uploadedImages.forEach(img => {
      URL.revokeObjectURL(img.previewUrl)
      if (img.croppedUrl) URL.revokeObjectURL(img.croppedUrl)
    })
    set({ uploadedImages: [], factionHint: undefined })
  },

  // Scanning
  isScanning: false,
  scanError: null,

  startScan: async () => {
    const { uploadedImages, factionHint } = get()
    if (uploadedImages.length === 0) return null

    set({ isScanning: true, scanError: null })

    try {
      const files = uploadedImages.map(img => img.file)
      const result = await detectFromImages(files, factionHint)

      // If user uploaded a real image, use it as the display image
      if (uploadedImages.length > 0 && !result.imageDataUrl) {
        const firstImg = uploadedImages[0]
        const url = firstImg.croppedUrl || firstImg.previewUrl
        result.imageDataUrl = url
      }

      await saveScan(result)
      set({ currentResult: result, isScanning: false })
      return result
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Scan failed'
      set({ isScanning: false, scanError: msg })
      return null
    }
  },

  // Results
  currentResult: null,
  setCurrentResult: (result) => set({ currentResult: result }),
  highlightedDetectionId: null,
  selectedDetectionId: null,
  setHighlightedDetection: (id) => set({ highlightedDetectionId: id }),
  setSelectedDetection: (id) => set({ selectedDetectionId: id }),
  groupingMode: 'faction',
  setGroupingMode: (mode) => set({ groupingMode: mode }),

  // Editing
  editDetection: (id, updates) => {
    set(s => {
      if (!s.currentResult) return s
      return {
        currentResult: {
          ...s.currentResult,
          detections: s.currentResult.detections.map(d =>
            d.id === id ? { ...d, ...updates } : d
          ),
        },
      }
    })
  },

  removeDetection: (id) => {
    set(s => {
      if (!s.currentResult) return s
      return {
        currentResult: {
          ...s.currentResult,
          detections: s.currentResult.detections.filter(d => d.id !== id),
        },
      }
    })
  },
}))
