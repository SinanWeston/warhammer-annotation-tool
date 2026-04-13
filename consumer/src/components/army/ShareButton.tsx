import { useState } from 'react'
import { useArmyStore } from '../../stores/armyStore'
import { armyToShareHash } from '../../utils/formatExport'

export default function ShareButton() {
  const army = useArmyStore(s => s.currentArmy)
  const [copied, setCopied] = useState(false)

  const handleShare = async () => {
    const hash = armyToShareHash(army)
    const url = `${window.location.origin}${window.location.pathname}#/army?share=${hash}`
    await navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={handleShare}
      className="px-3 py-1.5 bg-surface-3 border border-surface-4 text-gray-300 text-xs font-grim rounded hover:bg-surface-4"
    >
      {copied ? 'Link Copied!' : 'Share Link'}
    </button>
  )
}
