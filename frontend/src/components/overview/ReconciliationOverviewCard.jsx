import React from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

export default function ReconciliationOverviewCard({ summary, resolutionSummary }) {
  const total = summary?.total_settlement_batches ?? 0
  const matched = summary?.matched_batches ?? 0
  const autoResolved = resolutionSummary?.auto_resolved_count ?? 0
  const needsReview = resolutionSummary?.needs_human_review_count ?? 0
  const unmatched = Math.max(total - matched, 0)

  const segments = [
    {
      label: 'Matched',
      count: matched,
      color: '#10b981',
      className: 'green'
    },
    {
      label: 'Auto-resolved',
      count: autoResolved,
      color: '#0ea5e9',
      className: 'blue'
    },
    {
      label: 'Needs Review',
      count: needsReview,
      color: '#f59e0b',
      className: 'amber'
    },
    {
      label: 'Unmatched',
      count: unmatched,
      color: '#f43f5e',
      className: 'rose'
    }
  ]

  // Math for SVG Donut slices
  const radius = 50
  const circumference = 2 * Math.PI * radius
  let accumulatedPercent = 0

  const renderedSlices = segments.map((seg) => {
    const pct = total > 0 ? seg.count / total : 0
    const strokeDash = pct * circumference
    const offset = accumulatedPercent * circumference
    accumulatedPercent += pct

    return {
      ...seg,
      pctDisplay: (pct * 100).toFixed(1),
      strokeDasharray: `${strokeDash} ${circumference - strokeDash}`,
      strokeDashoffset: -offset
    }
  })

  return (
    <article className="saas-card" aria-label="Reconciliation Overview Card">
      <div className="card-header">
        <h2 className="card-title">Reconciliation Overview</h2>
      </div>

      <div className="recon-overview-content">
        {/* Left Multi-segment Donut */}
        <div className="recon-donut-wrap">
          <svg width="140" height="140" viewBox="0 0 140 140" style={{ transform: 'rotate(-90deg)' }}>
            {/* Background ring */}
            <circle
              cx="70"
              cy="70"
              r={radius}
              fill="transparent"
              stroke="#f1f5f9"
              strokeWidth="16"
            />
            {/* Slices */}
            {renderedSlices.map((slice, idx) => {
              if (slice.count <= 0) return null
              return (
                <circle
                  key={idx}
                  cx="70"
                  cy="70"
                  r={radius}
                  fill="transparent"
                  stroke={slice.color}
                  strokeWidth="16"
                  strokeDasharray={slice.strokeDasharray}
                  strokeDashoffset={slice.strokeDashoffset}
                  style={{ transition: 'stroke-dasharray 0.5s ease' }}
                />
              )
            })}
          </svg>
          <div className="recon-donut-center">
            <span className="recon-donut-count">{total}</span>
            <span className="recon-donut-sub">Total</span>
          </div>
        </div>

        {/* Right Legend */}
        <div className="recon-legend">
          {renderedSlices.map((slice) => (
            <div key={slice.label} className="legend-row">
              <div className="legend-left">
                <span className={`legend-dot ${slice.className}`} />
                <span className="legend-label">{slice.label}</span>
              </div>
              <span className="legend-val">
                {slice.count} ({slice.pctDisplay}%)
              </span>
            </div>
          ))}
        </div>
      </div>

      <Link to="/reconciliations" className="card-action-link" id="link-go-to-reconciliations">
        <span>Go to Reconciliations</span>
        <ArrowRight size={14} />
      </Link>
    </article>
  )
}
