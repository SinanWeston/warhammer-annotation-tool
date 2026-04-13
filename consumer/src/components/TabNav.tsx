import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/scan', label: 'Scan' },
  { to: '/results', label: 'Results' },
  { to: '/army', label: 'Army Builder' },
  { to: '/history', label: 'History' },
]

export default function TabNav() {
  return (
    <nav className="border-b border-surface-3 bg-surface-1">
      <div className="max-w-[1400px] mx-auto flex">
        {tabs.map(tab => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `px-5 py-3 text-sm font-grim tracking-wide border-b-2 transition-colors ${
                isActive
                  ? 'border-brass-light text-brass-light'
                  : 'border-transparent text-gothic-light hover:text-gray-300 hover:border-gothic-medium'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
