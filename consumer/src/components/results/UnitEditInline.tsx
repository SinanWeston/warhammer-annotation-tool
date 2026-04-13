import { useState } from 'react'
import type { Detection } from '../../types/detection'
import { useScanStore } from '../../stores/scanStore'

interface UnitEditInlineProps {
  detection: Detection
  onClose: () => void
}

export default function UnitEditInline({ detection, onClose }: UnitEditInlineProps) {
  const editDetection = useScanStore(s => s.editDetection)
  const [name, setName] = useState(detection.unitName)
  const [points, setPoints] = useState(detection.points)

  const handleSave = () => {
    editDetection(detection.id, { unitName: name, points })
    onClose()
  }

  return (
    <div className="bg-surface-3 border border-surface-4 rounded p-3 mt-1">
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div>
          <label className="text-[10px] text-gothic-light font-grim uppercase">Name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-brass"
          />
        </div>
        <div>
          <label className="text-[10px] text-gothic-light font-grim uppercase">Points</label>
          <input
            type="number"
            value={points}
            onChange={e => setPoints(Number(e.target.value))}
            className="w-full bg-surface-2 border border-surface-4 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:border-brass"
          />
        </div>
      </div>
      <div className="flex gap-2 justify-end">
        <button onClick={onClose} className="px-3 py-1 text-xs text-gothic-light hover:text-gray-300 font-grim">
          Cancel
        </button>
        <button onClick={handleSave} className="px-3 py-1 bg-brass text-gothic-darker rounded text-xs font-grim hover:bg-brass-light">
          Save
        </button>
      </div>
    </div>
  )
}
