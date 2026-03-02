import { useState, useEffect } from 'react'

const phrases = [
  'Analyzing battlefield...',
  'Identifying factions...',
  'Counting units...',
  'Scanning for heresy...',
]

export default function ScanAnimation() {
  const [phraseIndex, setPhraseIndex] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setPhraseIndex(prev => (prev + 1) % phrases.length)
    }, 2500)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="fixed inset-0 z-50 bg-gothic-darker/95 flex flex-col items-center justify-center gap-8">
      {/* Pulsing skull/aquila icon */}
      <div className="relative">
        <div className="w-24 h-24 rounded-full border-2 border-blue-400/40 flex items-center justify-center animate-pulse-glow text-blue-400">
          <svg className="w-14 h-14 text-blue-400 animate-glow-pulse" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" />
          </svg>
        </div>
        {/* Orbiting ring */}
        <div className="absolute inset-[-8px] rounded-full border border-blue-400/20 animate-spin" style={{ animationDuration: '3s' }} />
      </div>

      {/* Cycling text */}
      <p className="font-grim text-sm uppercase tracking-[0.3em] text-blue-300 animate-glow-pulse">
        {phrases[phraseIndex]}
      </p>

      {/* Progress bar */}
      <div className="w-48 h-1 bg-gothic-dark/40 rounded-full overflow-hidden">
        <div className="h-full bg-blue-400/60 rounded-full animate-scan-line" style={{
          width: '40%',
          animation: 'scan-progress 1.5s ease-in-out infinite'
        }} />
      </div>

      <style>{`
        @keyframes scan-progress {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(350%); }
        }
      `}</style>
    </div>
  )
}
