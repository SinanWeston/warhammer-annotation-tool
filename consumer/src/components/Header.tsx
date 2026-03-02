interface HeaderProps {
  currentPage?: string
  onInfoClick?: () => void
  onHistoryClick?: () => void
  onArmyClick?: () => void
  armyScanCount?: number
}

export default function Header({
  currentPage,
  onInfoClick,
  onHistoryClick,
  onArmyClick,
  armyScanCount = 0,
}: HeaderProps) {
  return (
    <header className="w-full py-4 px-4 safe-top">
      <div className="max-w-2xl mx-auto flex items-center justify-between">
        {/* Left nav */}
        <div className="flex gap-1 w-20">
          {onInfoClick && (
            <button
              onClick={onInfoClick}
              className="w-9 h-9 flex items-center justify-center rounded-lg text-gothic-light/50 hover:text-blue-400 hover:bg-white/5 transition-colors"
              title="Info"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <circle cx="12" cy="12" r="10" />
                <path strokeLinecap="round" d="M12 16v-4M12 8h.01" />
              </svg>
            </button>
          )}
        </div>

        {/* Center brand */}
        <div className="flex items-center gap-3">
          <svg className="w-7 h-7 text-blue-400/60" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2L8 6l-6 2 2 6-2 6 6 2 4-4 4 4 6-2-2-6 2-6-6-2-4-4zm0 4l2.5 2.5L17 10l-1.5 3.5L17 17l-3.5-1.5L12 18l-1.5-2.5L7 17l1.5-3.5L7 10l2.5-1.5L12 6z" />
          </svg>
          <div className="text-center">
            <h1 className="font-gothic font-bold text-lg tracking-wider text-white text-glow leading-none">
              BATTLE SCANNER
            </h1>
            <p className="font-grim text-[9px] uppercase tracking-[0.35em] text-gothic-light/40 mt-0.5">
              Warhammer 40K Detector
            </p>
          </div>
          <svg className="w-7 h-7 text-blue-400/60 scale-x-[-1]" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2L8 6l-6 2 2 6-2 6 6 2 4-4 4 4 6-2-2-6 2-6-6-2-4-4zm0 4l2.5 2.5L17 10l-1.5 3.5L17 17l-3.5-1.5L12 18l-1.5-2.5L7 17l1.5-3.5L7 10l2.5-1.5L12 6z" />
          </svg>
        </div>

        {/* Right nav */}
        <div className="flex gap-1 w-20 justify-end">
          {onHistoryClick && (
            <button
              onClick={onHistoryClick}
              className={`w-9 h-9 flex items-center justify-center rounded-lg transition-colors ${
                currentPage === 'history'
                  ? 'text-blue-400 bg-blue-400/10'
                  : 'text-gothic-light/50 hover:text-blue-400 hover:bg-white/5'
              }`}
              title="History"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <circle cx="12" cy="12" r="10" />
                <path strokeLinecap="round" d="M12 6v6l4 2" />
              </svg>
            </button>
          )}
          {onArmyClick && (
            <button
              onClick={onArmyClick}
              className={`relative w-9 h-9 flex items-center justify-center rounded-lg transition-colors ${
                currentPage === 'army'
                  ? 'text-amber-400 bg-amber-400/10'
                  : 'text-gothic-light/50 hover:text-amber-400 hover:bg-white/5'
              }`}
              title="Army"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 2l3 7h7l-5.5 4.5L18 21l-6-4.5L6 21l1.5-7.5L2 9h7l3-7z" />
              </svg>
              {armyScanCount > 0 && (
                <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-amber-500 text-black text-[10px] font-bold font-grim px-1">
                  {armyScanCount}
                </span>
              )}
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
