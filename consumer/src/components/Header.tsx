export default function Header() {
  return (
    <header className="border-b border-surface-3 bg-surface-1 px-6 py-3">
      <div className="max-w-[1400px] mx-auto flex items-center gap-3">
        <div className="w-8 h-8 rounded bg-brass flex items-center justify-center">
          <span className="text-gothic-darker font-gothic font-bold text-sm">BS</span>
        </div>
        <h1 className="font-gothic font-bold text-xl text-brass-light tracking-wider">
          BATTLE SCANNER
        </h1>
        <span className="text-xs text-gothic-light font-grim ml-2 mt-1">v2.0</span>
      </div>
    </header>
  )
}
