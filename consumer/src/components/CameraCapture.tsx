import { useRef, useState, useEffect, useCallback } from 'react'

interface CameraCaptureProps {
  onCapture: (blob: Blob, imageDataUrl: string) => void
}

export default function CameraCapture({ onCapture }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // 1.2 — streamRef instead of stream state: cleanup always reads the live value
  const streamRef = useRef<MediaStream | null>(null)
  const [facingMode, setFacingMode] = useState<'environment' | 'user'>('environment')
  const [cameraError, setCameraError] = useState<string | null>(null)
  // 2.5 — Camera loading state
  const [cameraReady, setCameraReady] = useState(false)

  const startCamera = useCallback(async () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    setCameraReady(false)
    setCameraError(null)

    try {
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      })
      streamRef.current = mediaStream

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream
        videoRef.current.onloadedmetadata = () => setCameraReady(true)
      }
    } catch (err: any) {
      // 2.6 — specific permission/device error messages (already implemented, kept)
      if (err.name === 'NotAllowedError') {
        setCameraError('Camera access denied. Please allow camera access in your browser settings.')
      } else if (err.name === 'NotFoundError') {
        setCameraError('No camera found on this device.')
      } else {
        setCameraError('Could not access camera. Try uploading a photo instead.')
      }
    }
  }, [facingMode])

  useEffect(() => {
    startCamera()
    return () => {
      // streamRef always has the current value — no stale closure bug
      streamRef.current?.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
  }, [facingMode])

  const capture = () => {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return

    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.drawImage(video, 0, 0)
    const dataUrl = canvas.toDataURL('image/jpeg', 0.9)

    canvas.toBlob(
      (blob) => { if (blob) onCapture(blob, dataUrl) },
      'image/jpeg',
      0.9
    )
  }

  const switchCamera = () => {
    setFacingMode(prev => prev === 'environment' ? 'user' : 'environment')
  }

  if (cameraError) {
    return (
      <div className="border-2 border-dashed border-gothic-medium/40 rounded-xl p-8 text-center">
        <div className="text-4xl mb-3">📷</div>
        <p className="text-gothic-light text-sm">{cameraError}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative w-full aspect-[4/3] rounded-xl overflow-hidden border-2 border-gothic-dark/60 shadow-glow-sm">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="w-full h-full object-cover"
        />

        {/* 2.5 — Camera initialisation loading overlay */}
        {!cameraReady && (
          <div className="absolute inset-0 flex items-center justify-center bg-gothic-darker/80">
            <p className="text-gothic-light/60 text-sm font-grim tracking-wider">Starting camera...</p>
          </div>
        )}

        {/* Scan line overlay */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-blue-400/60 to-transparent animate-scan-line" />
        </div>
        {/* Corner brackets */}
        <div className="absolute top-3 left-3 w-6 h-6 border-t-2 border-l-2 border-blue-400/50" />
        <div className="absolute top-3 right-3 w-6 h-6 border-t-2 border-r-2 border-blue-400/50" />
        <div className="absolute bottom-3 left-3 w-6 h-6 border-b-2 border-l-2 border-blue-400/50" />
        <div className="absolute bottom-3 right-3 w-6 h-6 border-b-2 border-r-2 border-blue-400/50" />
      </div>

      <canvas ref={canvasRef} className="hidden" />

      <div className="flex items-center gap-6">
        <button
          onClick={switchCamera}
          className="w-12 h-12 rounded-full bg-gothic-dark/60 border border-gothic-medium/40 flex items-center justify-center text-gothic-light hover:text-white transition-colors"
          aria-label="Switch camera"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
          </svg>
        </button>

        {/* Shutter — disabled until stream is ready */}
        <button
          onClick={capture}
          disabled={!cameraReady}
          className="w-[72px] h-[72px] rounded-full border-4 border-white/80 bg-transparent flex items-center justify-center hover:border-white transition-all group disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Capture photo"
        >
          <div className="w-14 h-14 rounded-full bg-white/90 group-hover:bg-white group-active:scale-90 transition-all animate-pulse-glow text-blue-400" />
        </button>

        <div className="w-12 h-12" />
      </div>
    </div>
  )
}
