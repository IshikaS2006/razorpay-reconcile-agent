import React from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

export default function RoutePlaceholder({
  title,
  subtitle,
  icon: Icon,
  badge = 'Coming Next in Workflow',
  children
}) {
  return (
    <div className="placeholder-page">
      {Icon && (
        <div className="placeholder-icon">
          <Icon size={28} />
        </div>
      )}
      <span className="placeholder-badge">{badge}</span>
      <h2 className="placeholder-title">{title}</h2>
      <p className="placeholder-desc">{subtitle}</p>

      {children}

      <div style={{ marginTop: '16px' }}>
        <Link to="/" className="btn-primary" style={{ display: 'inline-flex', padding: '8px 16px' }}>
          <ArrowLeft size={16} />
          <span>Back to Overview</span>
        </Link>
      </div>
    </div>
  )
}
