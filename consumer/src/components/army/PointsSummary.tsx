interface PointsSummaryProps {
  totalPoints: number
  pointsLimit: number
  totalModels: number
  percentage: number
  isOver: boolean
}

export default function PointsSummary({ totalPoints, pointsLimit, totalModels, percentage, isOver }: PointsSummaryProps) {
  const barColor = isOver ? 'bg-red-500' : percentage > 90 ? 'bg-orange-500' : 'bg-brass-light'

  return (
    <div className="bg-surface-2 border border-surface-3 rounded-lg p-4">
      <div className="flex items-baseline justify-between mb-2">
        <div>
          <span className={`text-2xl font-gothic font-bold ${isOver ? 'text-red-400' : 'text-brass-light'}`}>
            {totalPoints}
          </span>
          <span className="text-sm text-gothic-light font-grim"> / {pointsLimit} pts</span>
        </div>
        <span className="text-xs text-gothic-light font-grim">{totalModels} models</span>
      </div>
      <div className="w-full h-2 bg-surface-3 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.min(100, percentage)}%` }}
        />
      </div>
      {isOver && (
        <p className="text-xs text-red-400 mt-1 font-grim">
          Over by {totalPoints - pointsLimit} points
        </p>
      )}
    </div>
  )
}
