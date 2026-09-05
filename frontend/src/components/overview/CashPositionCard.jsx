import React from 'react'
import { Link } from 'react-router-dom'
import { MoreHorizontal, ArrowRight, Info } from 'lucide-react'

function formatInr(paise) {
  if (paise == null) return '—'
  const rupees = Number(paise || 0) / 100
  return `₹${rupees.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

export default function CashPositionCard({ cashPositionData, timeseriesData }) {
  const confirmedPaise = cashPositionData?.confirmed_total ?? null
  const atRiskPaise = cashPositionData?.at_risk_total ?? null

  const expectedInflowsPaise = (timeseriesData?.inflow_rows?.confirmed || [])
    .reduce((sum, row) => sum + Number(row.amount_paise || 0), 0)
    + (timeseriesData?.inflow_rows?.projected || [])
      .reduce((sum, row) => sum + Number(row.amount_paise || 0), 0)

  const expectedOutflowsPaise = (timeseriesData?.outflow_rows || [])
    .reduce((sum, row) => sum + Number(row.amount_paise || 0), 0)

  const hasLiveSnapshot = confirmedPaise != null || atRiskPaise != null || expectedInflowsPaise > 0 || expectedOutflowsPaise > 0

  return (
    <article className="saas-card" aria-label="Cash Position Card">
      <div className="card-header">
        <h2 className="card-title">Cash Position</h2>
        <button type="button" className="card-more-btn" title="More options" aria-label="More options">
          <MoreHorizontal size={18} />
        </button>
      </div>

      <div className="cash-position-content">
        <div className="cash-available-block">
          <span className="available-label">Available Cash</span>
          <span className="available-amount">{formatInr(confirmedPaise)}</span>
          <div className="kpi-trend" style={{ marginTop: '2px' }}>
            <span>{hasLiveSnapshot ? 'Live snapshot from latest run' : 'No cash snapshot available yet'}</span>
          </div>
        </div>

        <div className="cash-breakdown-list">
          <div className="cash-row">
            <span className="cash-row-label">Expected Inflows</span>
            <span className="cash-row-value">{formatInr(expectedInflowsPaise)}</span>
          </div>

          <div className="cash-row">
            <span className="cash-row-label">Expected Outflows</span>
            <span className="cash-row-value">{formatInr(expectedOutflowsPaise)}</span>
          </div>

          <div className="cash-row">
            <span className="cash-row-label">
              <span>At-risk Cash</span>
              <Info size={13} color="#94a3b8" title="Amounts flagged by unresolved or review-needed exceptions in the latest run" />
            </span>
            <span className="cash-row-value">{formatInr(atRiskPaise)}</span>
          </div>
        </div>
      </div>

      <Link to="/cash-position" className="card-action-link" id="link-view-cash-position">
        <span>View Cash Position</span>
        <ArrowRight size={14} />
      </Link>
    </article>
  )
}
