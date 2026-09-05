import React from 'react'
import { Calendar, ChevronDown } from 'lucide-react'

export default function TopHeader({
  title = 'Overview',
  subtitle = 'Reconcile settlements. Detect issues. Own your cash position.',
  dateRange = '20 May 2026 – 26 May 2026',
  showActions = true
}) {
  return (
    <header className="top-header">
      <div className="header-titles">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>

      {showActions && (
        <div className="header-actions">
          <button type="button" className="date-selector-btn" title="Filter by settlement date range">
            <Calendar size={15} color="#64748b" />
            <span>{dateRange}</span>
            <ChevronDown size={14} color="#64748b" />
          </button>
        </div>
      )}
    </header>
  )
}
