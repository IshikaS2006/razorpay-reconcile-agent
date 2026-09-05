import React from 'react'
import { NavLink, useLocation, Link } from 'react-router-dom'
import { Check } from 'lucide-react'

const NAV_ITEMS = [
  {
    to: '/reconciliations',
    label: 'Reconciliations',
    isActive: (p) => p.startsWith('/reconciliation'),
  },
  { to: '/forecast', label: 'Forecast' },
  { to: '/metrics',  label: 'Metrics'  },
]

export default function TopNav() {
  const { pathname } = useLocation()

  return (
    <header className="topnav">
      {/* Brand — clicking takes you to /reconciliations */}
      <Link to="/reconciliations" className="topnav-brand">
        <div className="topnav-brand-icon">
          <Check size={16} strokeWidth={3} />
        </div>
        <span className="topnav-brand-name">ClearLedger</span>
      </Link>

      {/* Tab links */}
      <nav className="topnav-tabs" aria-label="Main navigation">
        {NAV_ITEMS.map(item => {
          const active = item.isActive
            ? item.isActive(pathname)
            : pathname === item.to || pathname.startsWith(item.to + '/')
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`topnav-tab ${active ? 'topnav-tab-active' : ''}`}
            >
              {item.label}
            </NavLink>
          )
        })}
      </nav>
    </header>
  )
}
