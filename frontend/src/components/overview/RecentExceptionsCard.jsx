import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, ArrowRight } from 'lucide-react'
import { exLabel, fmtAmount, severityOf, isNeedsReview } from '../../utils/exceptions'

function ageOf(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3_600_000)
  if (h < 1) return '<1h ago'
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function RecentExceptionsCard({ liveExceptions = [], runId }) {
  const navigate = useNavigate()

  const openExceptions = (liveExceptions || []).filter(e => isNeedsReview(e.status))

  const items = openExceptions.slice(0, 3).map((e, idx) => ({
    id: e.reference_id || `exc-${idx}`,
    title: exLabel(e.exception_type),
    reference: e.reference_id || '—',
    amount: fmtAmount(e.amount_paise),
    time: ageOf(e.investigated_at),
    severity: severityOf(e).toLowerCase(),
    severityLabel: severityOf(e),
    refId: e.reference_id,
  }))

  const openItem = (item) => {
    if (runId && item.refId) {
      navigate(`/reconciliations/${runId}?exception=${encodeURIComponent(item.refId)}`)
    } else {
      navigate('/reconciliations')
    }
  }

  return (
    <article className="saas-card" aria-label="Recent Exceptions Card">
      <div className="card-header">
        <h2 className="card-title">Needs Review</h2>
        <p className="card-subtitle" style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
          Exception flags requiring human attention
        </p>
        <Link to={runId ? `/reconciliations/${runId}#report` : '/reconciliations'} className="kpi-label" style={{ color: '#2563eb', fontWeight: 600 }}>
          View all
        </Link>
      </div>

      <div className="exceptions-list">
        {items.length > 0 ? items.map((item) => (
          <div
            key={item.id}
            className="exception-item"
            onClick={() => openItem(item)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter') openItem(item) }}
          >
            <div className="exception-left">
              <div className={`exception-icon-box ${item.severity}`}>
                <AlertTriangle size={16} />
              </div>
              <div className="exception-titles">
                <span className="exception-name">{item.title}</span>
                <span className="exception-sub">{item.reference}</span>
              </div>
            </div>

            <div className="exception-right">
              <span className="exception-amount">{item.amount}</span>
              <span className="exception-time">{item.time}</span>
              <span className={`severity-badge ${item.severity}`}>
                {item.severityLabel}
              </span>
            </div>
          </div>
        )) : (
          <div className="empty-card-state">No review-needed exceptions in the latest run.</div>
        )}
      </div>

      <Link to={runId ? `/reconciliations/${runId}#report` : '/reconciliations'} className="card-action-link" id="link-view-all-exceptions">
        <span>View all exceptions</span>
        <ArrowRight size={14} />
      </Link>
    </article>
  )
}
