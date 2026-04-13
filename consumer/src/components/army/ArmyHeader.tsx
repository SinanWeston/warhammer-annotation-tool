import { useState } from 'react'
import { useArmyStore } from '../../stores/armyStore'
import FactionIcon from '../FactionIcon'

export default function ArmyHeader() {
  const army = useArmyStore(s => s.currentArmy)
  const setArmyName = useArmyStore(s => s.setArmyName)
  const setPointsLimit = useArmyStore(s => s.setPointsLimit)
  const [editingName, setEditingName] = useState(false)
  const [nameInput, setNameInput] = useState(army.name)

  const factions = [...new Set(army.units.map(u => u.faction))]

  const handleNameSave = () => {
    setArmyName(nameInput.trim() || 'New Army')
    setEditingName(false)
  }

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        {editingName ? (
          <input
            autoFocus
            value={nameInput}
            onChange={e => setNameInput(e.target.value)}
            onBlur={handleNameSave}
            onKeyDown={e => e.key === 'Enter' && handleNameSave()}
            className="bg-surface-2 border border-brass rounded px-3 py-1 text-xl font-gothic text-brass-light focus:outline-none"
          />
        ) : (
          <h2
            onClick={() => { setNameInput(army.name); setEditingName(true) }}
            className="font-gothic text-2xl text-brass-light cursor-pointer hover:text-brass"
            title="Click to rename"
          >
            {army.name}
          </h2>
        )}
        <div className="flex gap-1 ml-2">
          {factions.map(f => <FactionIcon key={f} faction={f} size="sm" />)}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs text-gothic-light font-grim">Points limit:</label>
        <select
          value={army.pointsLimit}
          onChange={e => setPointsLimit(Number(e.target.value))}
          className="bg-surface-2 border border-surface-3 rounded px-2 py-1 text-sm text-gray-200 font-grim focus:outline-none focus:border-brass"
        >
          <option value={500}>500</option>
          <option value={1000}>1000</option>
          <option value={1500}>1500</option>
          <option value={2000}>2000</option>
          <option value={2500}>2500</option>
          <option value={3000}>3000</option>
        </select>
      </div>
    </div>
  )
}
