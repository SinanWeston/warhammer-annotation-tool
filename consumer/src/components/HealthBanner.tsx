import { useState, useEffect, useRef } from 'react'

type HealthStatus = 'checking' | 'healthy' | 'degraded' | 'unavailable'

export default function HealthBanner() {
  const [status, setStatus] = useState<HealthStatus>('checking')
  const intervalRef = useRef<ReturnType<typeof setInterval>>()

  useEffect(() => {
    let mounted = true

    const check = async () => {
      try {
        const res = await fetch('/api/health', { signal: AbortSignal.timeout(5000) })
        if (!mounted) return
        if (res.ok) {
          const data = await res.json()
          setStatus(data.modelLoaded ? 'healthy' : 'degraded')
        } else {
          setStatus('unavailable')
        }
      } catch {
        if (mounted) setStatus('unavailable')
      }
    }

    check()
    intervalRef.current = setInterval(check, 10000)

    return () => {
      mounted = false
      clearInterval(intervalRef.current)
    }
  }, [])

  if (status === 'healthy' || status === 'checking') return null

  if (status === 'degraded') {
    return (
      <div className="mx-4 mb-2 flex items-center gap-2 bg-amber-900/40 border border-amber-500/30 rounded-lg px-4 py-2">
        <span className="text-amber-400 text-sm">&#9888;</span>
        <p className="text-amber-200 text-xs font-grim">
          Scanner model not loaded — detection may be unavailable
        </p>
      </div>
    )
  }

  return (
    <div className="mx-4 mb-2 flex items-center gap-2 bg-red-900/40 border border-red-500/30 rounded-lg px-4 py-2">
      <span className="text-red-400 text-sm">&#9679;</span>
      <p className="text-red-200 text-xs font-grim">
        Scanner unavailable — check backend connection
      </p>
    </div>
  )
}
