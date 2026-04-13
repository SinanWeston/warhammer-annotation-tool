import { getFactionColor, getFactionDisplayName } from '../utils/factions'

interface FactionIconProps {
  faction: string
  size?: 'sm' | 'md'
}

export default function FactionIcon({ faction, size = 'md' }: FactionIconProps) {
  const color = getFactionColor(faction)
  const name = getFactionDisplayName(faction)
  const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
  const px = size === 'sm' ? 'w-6 h-6 text-[10px]' : 'w-8 h-8 text-xs'

  return (
    <div
      className={`${px} rounded flex items-center justify-center font-grim font-bold text-white shrink-0`}
      style={{ backgroundColor: color }}
      title={name}
    >
      {initials}
    </div>
  )
}
