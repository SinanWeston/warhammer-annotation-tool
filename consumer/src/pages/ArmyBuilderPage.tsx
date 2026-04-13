import { useEffect } from 'react'
import { useArmyStore } from '../stores/armyStore'
import { usePointsCalculator } from '../hooks/usePointsCalculator'
import ArmyHeader from '../components/army/ArmyHeader'
import PointsSummary from '../components/army/PointsSummary'
import ArmyUnitRow from '../components/army/ArmyUnitRow'
import UnitSearchAdd from '../components/army/UnitSearchAdd'
import CompositionSuggestions from '../components/army/CompositionSuggestions'
import ExportMenu from '../components/army/ExportMenu'
import ShareButton from '../components/army/ShareButton'
import EmptyState from '../components/EmptyState'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { armyFromShareHash } from '../utils/formatExport'
import { generateId } from '../lib/id'
import type { Army } from '../types/army'

export default function ArmyBuilderPage() {
  const army = useArmyStore(s => s.currentArmy)
  const resetArmy = useArmyStore(s => s.resetArmy)
  const saveCurrentArmy = useArmyStore(s => s.saveCurrentArmy)
  const loadArmy = useArmyStore(s => s.loadArmy)
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { totalPoints, totalModels, percentage, isOver, remaining } = usePointsCalculator(army.units, army.pointsLimit)

  // Decode ?share= on mount, replace current army, then clear the URL param.
  useEffect(() => {
    const hash = searchParams.get('share')
    if (!hash) return
    const partial = armyFromShareHash(hash)
    if (partial?.units) {
      const now = new Date().toISOString()
      const shared: Army = {
        id: generateId(),
        name: partial.name ?? 'Shared Army',
        units: partial.units,
        createdAt: now,
        updatedAt: now,
        sourceScanIds: [],
        pointsLimit: partial.pointsLimit ?? 2000,
      }
      loadArmy(shared)
    }
    setSearchParams({}, { replace: true })
  }, [])

  return (
    <div className="grid grid-cols-[1fr_380px] gap-6">
      {/* Left column — army list */}
      <div>
        <ArmyHeader />

        <div className="mt-4">
          <PointsSummary
            totalPoints={totalPoints}
            pointsLimit={army.pointsLimit}
            totalModels={totalModels}
            percentage={percentage}
            isOver={isOver}
          />
        </div>

        <div className="mt-4">
          <UnitSearchAdd />
        </div>

        {army.units.length === 0 ? (
          <div className="mt-6">
            <EmptyState
              icon="+"
              title="Army is Empty"
              message="Search and add units above, or scan your miniatures to auto-populate."
              action={{ label: 'Scan Army', onClick: () => navigate('/scan') }}
            />
          </div>
        ) : (
          <div className="mt-4 space-y-2">
            {army.units.map(unit => (
              <ArmyUnitRow key={unit.id} unit={unit} />
            ))}
          </div>
        )}

        {/* Actions */}
        {army.units.length > 0 && (
          <div className="mt-6 flex items-center justify-between pt-4 border-t border-surface-3">
            <div className="flex gap-2">
              <ExportMenu />
              <ShareButton />
            </div>
            <div className="flex gap-2">
              <button
                onClick={resetArmy}
                className="px-3 py-1.5 text-xs text-gothic-light hover:text-red-400 font-grim"
              >
                Clear Army
              </button>
              <button
                onClick={saveCurrentArmy}
                className="px-4 py-1.5 bg-brass text-gothic-darker text-xs font-grim rounded hover:bg-brass-light"
              >
                Save Army
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Right column — suggestions */}
      <div className="border-l border-surface-3 pl-6">
        <CompositionSuggestions />
      </div>
    </div>
  )
}
