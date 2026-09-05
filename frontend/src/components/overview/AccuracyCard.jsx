import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

function formatPercent(val, defaultVal = '100%') {
  if (val == null) return defaultVal
  const num = Number(val)
  // If it's a decimal <= 1, convert to 100-based
  const pct = num <= 1.0 && num > 0 ? num * 100 : num
  return `${pct.toFixed(1).replace('.0', '')}%`
}

export default function AccuracyCard({ runId, accuracyReport, summary }) {
  const currentRunId = runId || summary?.run_id || '—'

  const matchRate = summary?.match_rate_pct != null
    ? `${summary.match_rate_pct.toFixed(1)}%`
    : accuracyReport?.matching?.match_rate_pct != null
      ? `${accuracyReport.matching.match_rate_pct.toFixed(1)}%`
      : '—'

  const numRate = matchRate === '—' ? 0 : (parseFloat(matchRate) || 0)

  // Circular progress math (radius 44, circumference 2 * PI * 44 = 276.46)
  const radius = 44
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (numRate / 100) * circumference

  const liveMetrics = accuracyReport?.live_metrics ?? {}
  const accuracyUnavailableNote = accuracyReport?.matching?.note || null
  const matchedCount = liveMetrics.exact_match_count != null && liveMetrics.fuzzy_match_count != null
    ? `${liveMetrics.exact_match_count + liveMetrics.fuzzy_match_count}`
    : '—'
  const unresolvedCount = liveMetrics.unresolved_settlement_count != null
    ? `${liveMetrics.unresolved_settlement_count}`
    : '—'
  const partialCreditCount = liveMetrics.partial_credit_count != null
    ? `${liveMetrics.partial_credit_count}`
    : '—'
  const duplicateCount = liveMetrics.duplicate_posting_count != null
    ? `${liveMetrics.duplicate_posting_count}`
    : '—'

  return (
    <article className="saas-card" aria-label="Accuracy Card">
      <div className="card-header">
        <h2 className="card-title">Accuracy (Run #{currentRunId})</h2>
      </div>

      <div className="accuracy-content">
        {/* Left Donut Progress Ring */}
        <div className="accuracy-donut-wrap">
          <svg width="120" height="120" viewBox="0 0 120 120" style={{ transform: 'rotate(-90deg)' }}>
            {/* Background track circle */}
            <circle
              cx="60"
              cy="60"
              r={radius}
              fill="transparent"
              stroke="#eff6ff"
              strokeWidth="9"
            />
            {/* Value progress circle */}
            <circle
              cx="60"
              cy="60"
              r={radius}
              fill="transparent"
              stroke="#1d4ed8"
              strokeWidth="9"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              style={{ transition: 'stroke-dashoffset 0.6s ease' }}
            />
          </svg>
          <div className="accuracy-donut-center">
            <span className="accuracy-donut-val">{matchRate}</span>
            <span className="accuracy-donut-label">Match Rate</span>
          </div>
        </div>

        {/* Right Metric Rows */}
        <div className="accuracy-metrics-list">
          <div className="accuracy-row">
            <span className="accuracy-label">Matched Settlements</span>
            <span className="accuracy-val">{matchedCount}</span>
          </div>

          <div className="accuracy-row">
            <span className="accuracy-label">Unresolved Settlements</span>
            <span className="accuracy-val">{unresolvedCount}</span>
          </div>

          <div className="accuracy-row">
            <span className="accuracy-label">Partial Credits</span>
            <span className="accuracy-val">{partialCreditCount}</span>
          </div>

          <div className="accuracy-row">
            <span className="accuracy-label">Duplicate Flags</span>
            <span className="accuracy-val">{duplicateCount}</span>
          </div>
          {accuracyUnavailableNote && (
            <div className="accuracy-row">
              <span className="accuracy-label">Accuracy Status</span>
              <span className="accuracy-val">{accuracyUnavailableNote}</span>
            </div>
          )}
        </div>
      </div>

      <Link to="/metrics" className="card-action-link" id="link-view-accuracy-report">
        <span>View full report</span>
        <ArrowRight size={14} />
      </Link>
    </article>
  )
}
