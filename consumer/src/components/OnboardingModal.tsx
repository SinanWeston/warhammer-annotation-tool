import { FACTIONS } from '../utils/factions'
import FactionIcon from './FactionIcon'

interface OnboardingModalProps {
  onDismiss: () => void
}

export default function OnboardingModal({ onDismiss }: OnboardingModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
      <div className="bg-gothic-dark border border-gothic-medium/40 rounded-2xl max-w-md w-full max-h-[85dvh] overflow-y-auto">
        {/* Header */}
        <div className="p-6 pb-4 text-center border-b border-gothic-medium/20">
          <h2 className="font-gothic text-2xl text-white text-glow tracking-wider">
            BATTLE SCANNER
          </h2>
          <p className="text-gothic-light/60 text-sm font-grim mt-2">
            Identify Warhammer 40K miniatures from photos
          </p>
        </div>

        {/* What it does */}
        <div className="p-6 pb-4">
          <h3 className="font-gothic text-sm text-blue-400 uppercase tracking-wider mb-3">
            How It Works
          </h3>
          <ul className="space-y-2 text-gothic-light/70 text-sm font-grim">
            <li className="flex gap-2">
              <span className="text-blue-400 shrink-0">1.</span>
              Take a photo of your miniatures or upload one
            </li>
            <li className="flex gap-2">
              <span className="text-blue-400 shrink-0">2.</span>
              AI detects and identifies each model by faction
            </li>
            <li className="flex gap-2">
              <span className="text-blue-400 shrink-0">3.</span>
              See counts, points estimates, and share results
            </li>
          </ul>
        </div>

        {/* Supported factions */}
        <div className="px-6 pb-4">
          <h3 className="font-gothic text-sm text-blue-400 uppercase tracking-wider mb-3">
            Supported Factions ({FACTIONS.length})
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {FACTIONS.map(f => (
              <div
                key={f.key}
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg border"
                style={{
                  borderColor: `${f.color}30`,
                  backgroundColor: `${f.color}08`,
                }}
              >
                <FactionIcon faction={f.key} color={f.color} size={20} />
                <span className="text-xs font-grim text-gray-300 truncate">
                  {f.displayName}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Photo tips */}
        <div className="px-6 pb-4">
          <h3 className="font-gothic text-sm text-amber-400 uppercase tracking-wider mb-3">
            Photo Tips
          </h3>
          <ul className="space-y-1.5 text-gothic-light/60 text-xs font-grim">
            <li>&#8226; Good lighting reduces misdetections</li>
            <li>&#8226; Get close — fill the frame with your models</li>
            <li>&#8226; Flat angle works better than top-down</li>
            <li>&#8226; Plain backgrounds improve accuracy</li>
          </ul>
        </div>

        {/* Dismiss */}
        <div className="p-6 pt-2">
          <button
            onClick={onDismiss}
            className="w-full py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-grim text-sm uppercase tracking-wider shadow-glow-blue transition-all min-h-[48px]"
          >
            Got It
          </button>
        </div>
      </div>
    </div>
  )
}
