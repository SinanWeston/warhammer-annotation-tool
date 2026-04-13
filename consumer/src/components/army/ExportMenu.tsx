import { useState } from 'react'
import { useArmyStore } from '../../stores/armyStore'
import { exportAsPdf, exportAsText, copyToClipboard } from '../../services/exportService'

export default function ExportMenu() {
  const army = useArmyStore(s => s.currentArmy)
  const [copied, setCopied] = useState(false)

  const handleText = async () => {
    const text = exportAsText(army)
    await copyToClipboard(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handlePdf = () => {
    exportAsPdf(army)
  }

  return (
    <div className="flex gap-2">
      <button
        onClick={handlePdf}
        className="px-3 py-1.5 bg-surface-3 border border-surface-4 text-gray-300 text-xs font-grim rounded hover:bg-surface-4"
      >
        Export PDF
      </button>
      <button
        onClick={handleText}
        className="px-3 py-1.5 bg-surface-3 border border-surface-4 text-gray-300 text-xs font-grim rounded hover:bg-surface-4"
      >
        {copied ? 'Copied!' : 'Copy as Text'}
      </button>
      <button
        disabled
        className="px-3 py-1.5 bg-surface-3 border border-surface-4 text-gothic-light text-xs font-grim rounded opacity-50 cursor-not-allowed"
        title="Coming soon"
      >
        BattleScribe
      </button>
    </div>
  )
}
