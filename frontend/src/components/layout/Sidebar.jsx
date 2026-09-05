import React from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  PlusCircle,
  FileSpreadsheet,
  TrendingUp,
  BarChart3,
  ChevronRight,
  ChevronDown,
  ArrowLeft,
  Check
} from 'lucide-react'

export default function Sidebar({ collapsed = false, onToggleCollapse }) {
  const location = useLocation()

  const navItems = [
    {
      to: '/',
      label: 'New Reconciliation',
      icon: PlusCircle,
      isActive: (pathname) => pathname === '/' || pathname === '/overview'
    },
    {
      to: '/reconciliations',
      label: 'Reconciliations',
      icon: FileSpreadsheet,
      isActive: (pathname) => pathname.startsWith('/reconciliation')
    },
    { to: '/forecast', label: 'Forecast', icon: TrendingUp },
    { to: '/metrics',  label: 'Metrics',  icon: BarChart3 },
  ]

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-top">
        {/* Brand Lockup */}
        <div className="brand-lockup">
          <div className="brand-icon-box" title="AI Finance Controller">
            <Check size={20} strokeWidth={3} />
          </div>
          {!collapsed && (
            <div className="brand-text">
              <span className="brand-name">Matchproof</span>
              <span className="brand-tagline">Finance Controller</span>
            </div>
          )}
        </div>

        {/* Navigation Menu */}
        <nav>
          <ul className="nav-menu">
            {navItems.map((item) => {
              const Icon = item.icon
              const isItemActive = item.isActive
                ? item.isActive(location.pathname)
                : location.pathname.startsWith(item.to)

              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    className={`nav-link ${isItemActive ? 'active' : ''}`}
                    title={collapsed ? item.label : undefined}
                  >
                    <div className="nav-link-left">
                      <Icon className="nav-icon" size={18} strokeWidth={1.8} />
                      {!collapsed && <span>{item.label}</span>}
                    </div>
                    {!collapsed && item.badge != null && (
                      <span className="nav-badge">{item.badge}</span>
                    )}
                  </NavLink>
                </li>
              )
            })}
          </ul>
        </nav>
      </div>

      {/* Sidebar Bottom: Merchant & User Cards */}
      <div className="sidebar-bottom">
        {!collapsed && (
          <>
            <div className="merchant-card" title="Switch organization">
              <div className="merchant-info">
                <span className="merchant-name">Acme Retail Pvt. Ltd.</span>
                <span className="merchant-role">Merchant</span>
              </div>
              <ChevronRight size={16} className="card-more-btn" />
            </div>

            <div className="profile-card" title="User account options">
              <div className="profile-left">
                <div className="avatar-initials">AM</div>
                <div className="profile-info">
                  <span className="profile-name">Arjun Mehta</span>
                  <span className="profile-title">Finance Manager</span>
                </div>
              </div>
              <ChevronDown size={16} className="card-more-btn" />
            </div>
          </>
        )}

        <button
          type="button"
          className="collapse-btn"
          onClick={onToggleCollapse}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <ArrowLeft size={16} style={{ transform: collapsed ? 'rotate(180deg)' : 'none' }} />
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  )
}
