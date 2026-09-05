import React, { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import { BarChart3, ChevronDown, RefreshCw, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'

const API_URL = 'http://127.0.0.1:8000'

// Only exception types that represent a Razorpay settlement failing to match.
// Bank-side noise (unexplained_ledger_row) and order-DB exceptions
// (phantom_charge, ghost_order) are excluded — they don't indicate a
// Razorpay settlement problem.
const RAZORPAY_EXCEPTION_TYPES = {
  unresolved_settlement: { bar: '#e8353e', legend: '#e8353e', label: 'Unmatched Settlement' },
  amount_mismatch:       { bar: '#e05c2b', legend: '#e05c2b', label: 'Amount Mismatch' },
  timing_lag:            { bar: '#f0a500', legend: '#f0a500', label: 'Timing Lag' },
  duplicate_posting:     { bar: '#6c5ecf', legend: '#6c5ecf', label: 'Duplicate' },
  tax_line_mismatch:     { bar: '#0ea5e9', legend: '#0ea5e9', label: 'Tax Mismatch' },
}

// Ordered for the stacked bar display
const SEGMENT_ORDER = [
  'unresolved_settlement',
  'amount_mismatch',
  'timing_lag',
  'duplicate_posting',
  'tax_line_mismatch',
]

function pct(val) {
  if (val == null) return '—'
  return `${Number(val).toFixed(1)}%`
}

function num(val, fallback = '—') {
  if (val == null) return fallback
  return Number(val).toLocaleString()
}

export default function MetricsPage() {
  const [runs, setRuns]           = useState([])
  const [selectedRunId, setSelectedRunId] = useState(null)
  const [runDetail, setRunDetail] = useState(null)       // /runs/:id
  const [report, setReport]       = useState(null)       // /accuracy-report/:id
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)

  /* ── fetch run list once ── */
  const fetchRuns = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/runs`, { timeout: 5000 })
      const list = res.data || []
      setRuns(list)
      if (list.length > 0) {
        setSelectedRunId(list[0].run_id)
      }
    } catch {
      setError('Could not load runs. Make sure the backend is running.')
      setLoading(false)
    }
  }, [])

  /* ── fetch detail + report for selected run ── */
  const fetchRunData = useCallback(async (runId) => {
    if (!runId) return
    setLoading(true)
    setError('')
    try {
      const [detailRes, reportRes] = await Promise.allSettled([
        axios.get(`${API_URL}/runs/${runId}`, { timeout: 5000 }),
        axios.get(`${API_URL}/accuracy-report/${runId}`, { timeout: 5000 }),
      ])
      if (detailRes.status === 'fulfilled') setRunDetail(detailRes.value.data)
      if (reportRes.status === 'fulfilled') setReport(reportRes.value.data)
    } catch {
      setError('Failed to load metrics for this run.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchRuns() }, [fetchRuns])
  useEffect(() => { if (selectedRunId) fetchRunData(selectedRunId) }, [selectedRunId, fetchRunData])

  /* ── derived values ── */
  const matching   = report?.matching   ?? {}
  const liveMetrics = report?.live_metrics ?? {}
  const throughput = report?.throughput ?? {}

  const summary = runDetail?.summary ?? {}

  // Razorpay settlement volume — only settlement-side numbers
  const totalSettlements = summary.total_settlement_batches ?? 0
  const matchedSettlements = summary.matched_batches ?? 0
  // True unmatched = settlements that could not be confirmed in the bank
  // This matches the "Could Not Confirm" number shown on the run detail page
  const unmatchedSettlements = Math.max(0, totalSettlements - matchedSettlements)

  // Razorpay-relevant exceptions only
  const allExceptions = runDetail?.exceptions ?? []
  const razorpayExceptions = allExceptions.filter(
    ex => ex.exception_type in RAZORPAY_EXCEPTION_TYPES
  )

  // Needs Review = razorpay exceptions that still need human attention
  const razorpayNeedsReview = razorpayExceptions.filter(
    ex => ex.status === 'needs_human_review' || ex.status === 'needs_review' || !ex.status
  ).length

  // Auto-resolved = razorpay exceptions closed automatically
  const razorpayAutoResolved = razorpayExceptions.filter(
    ex => ex.status === 'auto_resolved' || ex.status === 'resolved'
  ).length

  // Exception breakdown — Razorpay-relevant only
  const exBreakdown = razorpayExceptions.reduce((acc, ex) => {
    acc[ex.exception_type] = (acc[ex.exception_type] || 0) + 1
    return acc
  }, {})
  const totalRazorpayExceptions = razorpayExceptions.length

  const activeSegments = SEGMENT_ORDER.filter(t => exBreakdown[t] > 0)

  const selectedRunLabel = runs.find(r => r.run_id === selectedRunId)
  const runLabel = selectedRunLabel ? `Run #${selectedRunLabel.run_id}` : '—'

  return (
    <div className="metrics-page">
      {/* ── Page Header ── */}
      <header className="metrics-header">
        <div className="metrics-title-block">
          <div className="metrics-title-row">
            <BarChart3 size={20} className="metrics-title-icon" strokeWidth={2} />
            <h1>Metrics</h1>
            {selectedRunId && (
              <Link
                to={`/reconciliations/${selectedRunId}`}
                className="metrics-view-report-btn"
                title="Open full reconciliation report"
              >
                <ExternalLink size={13} />
                View Report
              </Link>
            )}
          </div>
          <p className="metrics-subtitle">Track performance and accuracy</p>
        </div>

        {/* Run selector */}
        <div className="metrics-run-selector">
          <button
            type="button"
            className="run-selector-btn"
            onClick={() => setDropdownOpen(o => !o)}
            aria-haspopup="listbox"
            aria-expanded={dropdownOpen}
          >
            <span>{runLabel}</span>
            <ChevronDown size={14} />
          </button>

          {dropdownOpen && runs.length > 0 && (
            <ul className="run-selector-dropdown" role="listbox">
              {runs.map(r => (
                <li
                  key={r.run_id}
                  role="option"
                  aria-selected={r.run_id === selectedRunId}
                  className={`run-dropdown-item ${r.run_id === selectedRunId ? 'active' : ''}`}
                  onClick={() => { setSelectedRunId(r.run_id); setDropdownOpen(false) }}
                >
                  Run #{r.run_id}
                  {r.run_at && (
                    <span className="run-dropdown-date">
                      {new Date(r.run_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </header>

      {/* ── Error banner ── */}
      {error && (
        <div className="metrics-error-banner" role="alert">
          {error}
          <button
            type="button"
            onClick={() => fetchRunData(selectedRunId)}
            className="metrics-retry-btn"
          >
            <RefreshCw size={13} />
            Retry
          </button>
        </div>
      )}

      {/* ── Loading skeleton ── */}
      {loading && !error && (
        <div className="metrics-loading">
          <div className="metrics-skeleton-grid">
            <div className="metrics-skeleton-card" />
            <div className="metrics-skeleton-card" />
          </div>
          <div className="metrics-skeleton-bar" />
        </div>
      )}

      {/* ── Main content ── */}
      {!loading && !error && (
        <>
          {/* Top two-column cards */}
          <div className="metrics-top-grid">
            {/* Matching Metrics — Razorpay settlement matching only */}
            <section className="metrics-card" aria-label="Matching Metrics">
              <h2 className="metrics-card-title">Matching Metrics</h2>
              <div className="metrics-rows">
                <MetricRow label="Settlement Match Rate" value={summary.match_rate_pct != null ? pct(summary.match_rate_pct) : pct(matching.match_rate_pct)} />
                <MetricRow label="Matched Settlements" value={num(matching.matched_records)} />
                <MetricRow label="Exact Matches" value={num(liveMetrics.exact_match_count)} />
                <MetricRow label="Fuzzy Matches" value={num(liveMetrics.fuzzy_match_count)} />
                <MetricRow label="Partial Credits" value={num(liveMetrics.partial_credit_count)} />
              </div>
            </section>

            {/* Volume Overview — settlement-side numbers only */}
            <section className="metrics-card" aria-label="Volume Overview">
              <h2 className="metrics-card-title">Volume Overview</h2>
              <div className="metrics-rows">
                <MetricRow label="Total Settlements"    value={num(totalSettlements)}      />
                <MetricRow label="Matched"              value={num(matchedSettlements)}    />
                <MetricRow label="Could Not Confirm"    value={num(unmatchedSettlements)}  />
                <MetricRow label="Auto-resolved"        value={num(razorpayAutoResolved)}  />
                <MetricRow label="Needs Review"         value={num(razorpayNeedsReview)}   />
              </div>
            </section>
          </div>

          {/* Exception Breakdown — Razorpay settlement exceptions only */}
          <section className="metrics-card metrics-exception-card" aria-label="Exception Breakdown">
            <div className="exception-breakdown-header">
              <div>
                <h2 className="metrics-card-title">Exception Breakdown</h2>
                <p className="exception-breakdown-scope">Razorpay settlement exceptions only</p>
              </div>
              <span className="exception-total-badge">{totalRazorpayExceptions} total</span>
            </div>

            {totalRazorpayExceptions === 0 ? (
              <p className="exception-empty">No settlement exceptions for this run.</p>
            ) : (
              <>
                {/* Stacked bar */}
                <div className="exception-stacked-bar" role="img" aria-label="Settlement exception type distribution">
                  {activeSegments.map(type => {
                    const count = exBreakdown[type] || 0
                    const widthPct = (count / totalRazorpayExceptions) * 100
                    const color = RAZORPAY_EXCEPTION_TYPES[type]?.bar ?? '#94a3b8'
                    return (
                      <div
                        key={type}
                        className="exception-bar-segment"
                        style={{ width: `${widthPct}%`, background: color }}
                        title={`${RAZORPAY_EXCEPTION_TYPES[type]?.label ?? type}: ${count}`}
                      />
                    )
                  })}
                </div>

                {/* Legend */}
                <div className="exception-legend">
                  {activeSegments.map(type => {
                    const count = exBreakdown[type] || 0
                    const cfg = RAZORPAY_EXCEPTION_TYPES[type] ?? { legend: '#94a3b8', label: type }
                    return (
                      <span key={type} className="exception-legend-item">
                        <span
                          className="exception-legend-dot"
                          style={{ background: cfg.legend }}
                          aria-hidden="true"
                        />
                        {cfg.label} ({count})
                      </span>
                    )
                  })}
                </div>
              </>
            )}
          </section>

          {/* ── Processing Performance ── */}
          <div className="metrics-top-grid">
            <section className="metrics-card" aria-label="Processing Performance">
              <h2 className="metrics-card-title">Processing Performance</h2>
              <div className="metrics-rows">
                <MetricRow label="Records Processed"  value={num(throughput.total_records_processed)} />
                <MetricRow label="Processing Time"    value={throughput.total_time_sec != null ? `${Number(throughput.total_time_sec).toFixed(2)}s` : '—'} />
                <MetricRow label="Throughput"         value={throughput.records_per_sec != null ? `${Number(throughput.records_per_sec).toFixed(1)} rec/s` : '—'} />
              </div>
            </section>

            {/* Resolution Summary — scoped to Razorpay settlement exceptions */}
            <section className="metrics-card" aria-label="Resolution Summary">
              <h2 className="metrics-card-title">Resolution Summary</h2>
              <div className="metrics-rows">
                <MetricRow label="Settlement Exceptions" value={num(totalRazorpayExceptions)} />
                <MetricRow label="Unresolved Settlements" value={num(liveMetrics.unresolved_settlement_count)} />
                <MetricRow label="Duplicate Flags" value={num(liveMetrics.duplicate_posting_count)} />
                <MetricRow label="Refund Exceptions" value={num(liveMetrics.refund_exception_count)} />
                <MetricRow label="Needs Human Review" value={num(razorpayNeedsReview)} />
              </div>
            </section>
          </div>
        </>
      )}

      {/* Close dropdown on outside click */}
      {dropdownOpen && (
        <div
          className="metrics-dropdown-overlay"
          onClick={() => setDropdownOpen(false)}
          aria-hidden="true"
        />
      )}
    </div>
  )
}

function MetricRow({ label, value }) {
  return (
    <div className="metric-row">
      <span className="metric-row-label">{label}</span>
      <strong className="metric-row-value">{value}</strong>
    </div>
  )
}
