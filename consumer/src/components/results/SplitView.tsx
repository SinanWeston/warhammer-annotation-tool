import type { ReactNode } from 'react'

interface SplitViewProps {
  left: ReactNode
  right: ReactNode
}

export default function SplitView({ left, right }: SplitViewProps) {
  return (
    <div className="grid grid-cols-[55fr_45fr] gap-6 items-start">
      <div>{left}</div>
      <div className="max-h-[calc(100vh-200px)] overflow-y-auto scrollbar-thin pr-1">
        {right}
      </div>
    </div>
  )
}
