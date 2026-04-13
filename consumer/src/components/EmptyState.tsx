interface EmptyStateProps {
  icon?: string
  title: string
  message: string
  action?: { label: string; onClick: () => void }
}

export default function EmptyState({ icon = '?', title, message, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="text-4xl mb-4 opacity-40">{icon}</div>
      <h3 className="text-lg font-gothic text-gray-300 mb-2">{title}</h3>
      <p className="text-sm text-gothic-light max-w-md">{message}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 px-4 py-2 bg-brass text-gothic-darker rounded font-grim text-sm hover:bg-brass-light transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
