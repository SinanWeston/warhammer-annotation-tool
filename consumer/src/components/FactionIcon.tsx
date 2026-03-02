import { formatFactionName } from '../utils/factionDisplay'

interface FactionIconProps {
  faction: string
  color: string
  size?: number
}

export default function FactionIcon({ faction, color, size = 20 }: FactionIconProps) {
  const initials = formatFactionName(faction)
    .split(' ')
    .slice(0, 2)
    .map(w => w[0])
    .join('')

  return (
    <div
      className="rounded flex items-center justify-center font-gothic font-bold shrink-0"
      style={{
        width: size,
        height: size,
        backgroundColor: `${color}20`,
        border: `1px solid ${color}50`,
        color,
        fontSize: Math.round(size * 0.42),
        lineHeight: 1,
      }}
    >
      {initials}
    </div>
  )
}
