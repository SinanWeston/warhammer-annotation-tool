import { useState } from 'react'
import axios from 'axios'
import CameraCapture from '../components/CameraCapture'
import PhotoUpload from '../components/PhotoUpload'
import ScanAnimation from '../components/ScanAnimation'
import { DetectionResult } from '../types/detection'
import { resizeImage } from '../utils/resizeImage'

interface ScanPageProps {
  onDetection: (result: DetectionResult, imageDataUrl: string) => void
}

export default function ScanPage({ onDetection }: ScanPageProps) {
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingBlob, setPendingBlob] = useState<Blob | null>(null)
  const [pendingDataUrl, setPendingDataUrl] = useState<string | null>(null)

  const submitImage = async (blob: Blob, imageDataUrl: string) => {
    // 4.2 — Offline check
    if (!navigator.onLine) {
      setError('No internet connection. Scanning requires a connection to the server.')
      return
    }

    setPendingBlob(blob)
    setPendingDataUrl(imageDataUrl)
    setScanning(true)
    setError(null)

    // 1.1 — AbortController timeout (30s)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 30000)

    try {
      // 4.1 — Resize before upload (max 1280px)
      const resized = await resizeImage(blob)

      const formData = new FormData()
      formData.append('image', resized, 'scan.jpg')

      const response = await axios.post<{ success: boolean; data: DetectionResult }>(
        '/api/detect',
        formData,
        {
          signal: controller.signal,
          headers: { 'Content-Type': 'multipart/form-data' },
        }
      )

      if (response.data.success) {
        if (navigator.vibrate) navigator.vibrate(100)
        onDetection(response.data.data, imageDataUrl)
      }
    } catch (err: any) {
      if (axios.isCancel(err) || err.name === 'CanceledError' || err.name === 'AbortError') {
        setError('Scan timed out — please try again.')
      } else {
        const message = err.response?.data?.error?.message || 'Detection failed. Please try again.'
        setError(message)
      }
    } finally {
      clearTimeout(timeout)
      setScanning(false)
    }
  }

  // 2.1 — Retry with same image
  const handleRetry = () => {
    if (pendingBlob && pendingDataUrl) {
      submitImage(pendingBlob, pendingDataUrl)
    }
  }

  if (scanning) {
    return <ScanAnimation />
  }

  return (
    <div className="w-full flex flex-col gap-6 animate-fade-in-down pt-4">
      {error && (
        <div className="bg-red-900/40 border border-red-500/50 rounded-lg p-4">
          <p className="text-red-200 text-sm">{error}</p>
          {pendingBlob && (
            <button
              onClick={handleRetry}
              className="mt-3 w-full py-2 rounded-lg bg-red-700/60 hover:bg-red-700 text-red-100 font-grim text-xs uppercase tracking-wider transition-colors min-h-[44px]"
            >
              Try Again
            </button>
          )}
        </div>
      )}

      <CameraCapture onCapture={submitImage} />

      <div className="flex items-center gap-4">
        <div className="flex-1 h-px bg-gothic-medium/30" />
        <span className="text-gothic-light text-sm font-grim uppercase tracking-widest">or</span>
        <div className="flex-1 h-px bg-gothic-medium/30" />
      </div>

      <PhotoUpload onUpload={submitImage} />
    </div>
  )
}
