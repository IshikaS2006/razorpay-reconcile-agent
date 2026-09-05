import React, { useEffect, useState, useCallback } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import axios from 'axios'
import QueryBox from '../components/QueryBox'
import {
  CheckCircle2, AlertTriangle, Clock, ArrowRight, ChevronRight,
  Download, ArrowLeft, BarChart3, Wallet, TrendingUp,
  ShieldCheck, AlertCircle, Info, Activity, X, MessageSquare,
  Search, ChevronDown
} from 'lucide-react'

const API = 'http://127.0.0.1:8000'

function fmt(n) {
  if (n == null) return '—'
  return '₹' + Number(n).toLocaleString('en-IN')
}
function pct(v) {
  if (v == null) return '—'
  return Number(v).toFixed(1) + '%'
}
function runLabel(id) {
  return '#' + String(id).padStart(3, '0')
}
function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true
  })
}
function severityOf(exc) {
  const t = (exc.exception_type || '').toLowerCase()
  if (t.includes('missing') || t.includes('phantom')) return 'high'
  if (t.includes('amount') || t.includes('discrepancy') || t.includes('mismatch')) return 'medium'
  return 'low'
}
function exceptionLabel(type) {
  return (type || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
function amountFromPaise(paise) {
  if (paise == null) return null
  return paise / 100
}

function matchAmounts(match, fallbackExpectedPaise = null) {
  const expectedPaise = match?.expected_amount_paise ?? match?.settled_amount ?? fallbackExpectedPaise
  const actualPaise = match?.actual_amount_paise ?? match?.settled_amount ?? null
  const gapPaise = match?.amount_gap_paise ?? (expectedPaise != null && actualPaise != null ? Math.abs(expectedPaise - actualPaise) : null)
  return {
    expected: amountFromPaise(expectedPaise),
    actual: amountFromPaise(actualPaise),
    gap: amountFromPaise(gapPaise),
  }
}

function KpiCard({ label, value, sub, color, icon: Icon }) {
  return (
    <div className="rd-kpi-card">
      {Icon && <div className="rd-kpi-icon" style={{ background: color + '18', color }}><Icon size={16} /></div>}
      <div className="rd-kpi-val" style={{ color: color || 'var(--text-primary)' }}>{value}</div>
      <div className="rd-kpi-label">{label}</div>
      {sub && <div className="rd-kpi-sub">{sub}</div>}
    </div>
  )
}

function StatusBadge({ status }) {
  const map = {
    matched: { label: 'Matched', cls: 'badge-green' },
    needs_human_review: { label: 'Needs Review', cls: 'badge-rose' },
    needs_review: { label: 'Needs Review', cls: 'badge-rose' },
    auto_resolved: { label: 'Auto-resolved', cls: 'badge-green' },
    resolved: { label: 'Resolved', cls: 'badge-green' },
    escalated: { label: 'Escalated', cls: 'badge-amber' },
    explained: { label: 'Explained', cls: 'badge-blue' },
  }
  const s = map[status] || { label: status || 'Open', cls: 'badge-gray' }
  return <span className={`exc-badge ${s.cls}`}>{s.label}</span>
}

function SeverityDot({ level }) {
  const cls = { high: 'sev-high', medium: 'sev-medium', low: 'sev-low' }[level] || 'sev-low'
  return <span className={`sev-dot ${cls}`}>{level}</span>
}

function MatchRateRing({ rate }) {
  const r = 52, cx = 60, cy = 60
  const circ = 2 * Math.PI * r
  const filled = circ * (rate / 100)
  const gap = circ - filled
  return (
    <svg width={120} height={120} viewBox="0 0 120 120">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#e2e8f0" strokeWidth={10} />
      <circle cx={cx} cy={cy} r={r} fill="none"
        stroke="#1e56a0" strokeWidth={10}
        strokeDasharray={`${filled} ${gap}`}
        strokeLinecap="round"
        transform="rotate(-90 60 60)"
      />
      <text x={cx} y={cy - 6} textAnchor="middle" fontSize={18} fontWeight={700} fill="#0f172a">{rate.toFixed(1)}</text>
      <text x={cx} y={cy + 10} textAnchor="middle" fontSize={11} fill="#64748b">% match</text>
    </svg>
  )
}

/* ---------------------------------------------------------------------
   NEW: Reconciliation breakdown section
   This was previously computed (matchedPct, excPct, excByType) but never
   rendered anywhere in the page. This component fills that gap and
   matches the "Reconciliation breakdown" block shown in the design:
   segmented progress bar + legend, an info callout explaining the
   matched/unresolved/exception distinction, and pills per exception type.
--------------------------------------------------------------------- */
function ReconciliationBreakdown({ matched, totalRec, matchedPct, excPct, excByType }) {
  const unresolved = Math.max(totalRec - matched, 0)
  const hasBreakdown = totalRec > 0
  const excEntries = Object.entries(excByType)

  return (
    <section className="rd-section rd-page-wide">
      <div className="rd-section-header">
        <div>
          <h2 className="rd-section-title">Reconciliation breakdown</h2>
          <p className="rd-section-sub">Record-level reconciliation results. Exceptions are independent anomaly checks.</p>
        </div>
      </div>

      {hasBreakdown && (
        <div className="rd-breakdown-bar">
          <div className="rd-breakdown-bar-track">
            <div className="rd-breakdown-bar-matched" style={{ width: `${matchedPct}%` }} />
            <div className="rd-breakdown-bar-unresolved" style={{ width: `${excPct}%` }} />
          </div>
          <div className="rd-breakdown-legend">
            <span className="rd-legend-item">
              <span className="rd-legend-dot rd-legend-dot-matched" /> Matched Records ({matched})
            </span>
            <span className="rd-legend-item">
              <span className="rd-legend-dot rd-legend-dot-unresolved" /> Unresolved Records ({unresolved})
            </span>
          </div>
        </div>
      )}

      <div className="rd-breakdown-info">
        <Info size={14} />
        <span>
          <strong>Matched</strong> = settlement records successfully reconciled.{' '}
          <strong>Unresolved</strong> = settlement records that could not be reconciled.
          Exceptions are separate anomaly checks that can exist independently of match status.
        </span>
      </div>

      {excEntries.length > 0 && (
        <div className="rd-breakdown-pills">
          {excEntries.map(([type, count]) => (
            <span key={type} className="rd-breakdown-pill">
              {type} <strong>{count}</strong>
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

function MatchesTable({ matches, onMatchSelect, selectedItem }) {
  if (!matches || matches.length === 0) return null

  return (
    <section className="rd-section">
      <div className="rd-section-header">
        <div>
          <h2 className="rd-section-title">Matched settlements</h2>
          <p className="rd-section-sub">Select a settlement to inspect the source records and matching decision.</p>
        </div>
        <span className="section-count">{matches.length} matched</span>
      </div>
      <div className="exc-table-wrap">
        <table className="exc-table">
          <thead><tr><th>Settlement</th><th>Ledger entry</th><th>Amount</th><th>Tier</th><th>Confidence</th><th>Action</th></tr></thead>
          <tbody>
            {matches.map((match, index) => {
              const isSelected = selectedItem?.kind === 'match' && selectedItem.data.settlement_id === match.settlement_id
              return (
                <tr key={`${match.settlement_id}-${index}`} className={`exc-row ${isSelected ? 'exc-row-selected' : ''}`} onClick={() => onMatchSelect(match)}>
                  <td><span className="exc-ref">{match.settlement_id || '—'}</span></td>
                  <td><span className="rd-inv-mono">{match.matched_entry_id || '—'}</span></td>
                  <td><span className="exc-amount">{fmt(match.settled_amount)}</span></td>
                  <td>{match.tier == null ? '—' : `Tier ${match.tier}`}</td>
                  <td>{match.confidence == null ? '—' : `${Math.round(match.confidence * 100)}%`}</td>
                  <td><button className="exc-investigate-btn" onClick={e => { e.stopPropagation(); onMatchSelect(match) }}>View details <ChevronRight size={12} /></button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ExceptionsTable({ exceptions, onExceptionSelect, selectedItem }) {
  if (!exceptions || exceptions.length === 0) return null
  const open = exceptions.filter(e => e.status !== 'auto_resolved' && e.status !== 'resolved' && e.status !== 'reviewed')
  if (open.length === 0) return null

  return (
    <section id="needs-review" className="rd-section">
      <div className="rd-section-header">
        <div>
          <h2 className="rd-section-title">Needs Review</h2>
          <p className="rd-section-sub">{open.length} exception{open.length !== 1 ? 's' : ''} requiring human attention. These are anomaly flags detected during reconciliation checks.</p>
        </div>
      </div>
      <div className="exc-table-wrap">
        <table className="exc-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Exception Type</th>
              <th>Reference</th>
              <th>Amount</th>
              <th>Description</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {open.map((exc, i) => {
              const sev = severityOf(exc)
              const amount = amountFromPaise(exc.amount_paise)
              const isSelected = selectedItem?.kind === 'exception' && selectedItem.data.reference_id === exc.reference_id
              return (
                <tr 
                  key={i} 
                  className={`exc-row ${isSelected ? 'exc-row-selected' : ''}`}
                  onClick={() => onExceptionSelect(exc)}
                >
                  <td><SeverityDot level={sev} /></td>
                  <td>
                    <div className="exc-type">{exceptionLabel(exc.exception_type)}</div>
                    <div className="exc-source">{exc.source}</div>
                  </td>
                  <td><span className="exc-ref">{exc.reference_id || '—'}</span></td>
                  <td><span className="exc-amount">{amount ? fmt(amount) : '—'}</span></td>
                  <td><span className="exc-detail">{exc.detail || exc.recommended_action || '—'}</span></td>
                  <td><StatusBadge status={exc.status} /></td>
                  <td onClick={e => e.stopPropagation()}>
                    <button
                      className="exc-investigate-btn"
                      onClick={() => onExceptionSelect(exc)}
                    >
                      Investigate <ChevronRight size={12} />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function AutoResolvedSection({ exceptions }) {
  if (!exceptions || exceptions.length === 0) return null
  const resolved = exceptions.filter(e => e.status === 'auto_resolved' || e.status === 'resolved')
  if (resolved.length === 0) return null

  return (
    <section className="rd-section">
      <div className="rd-section-header">
        <div>
          <h2 className="rd-section-title">Auto-resolved Exceptions</h2>
          <p className="rd-section-sub">{resolved.length} exception{resolved.length !== 1 ? 's' : ''} resolved automatically by the controller. These anomaly flags were deemed safe to close without human intervention.</p>
        </div>
      </div>
      <div className="autores-grid">
        {resolved.map((exc, i) => {
          const amount = amountFromPaise(exc.amount_paise)
          return (
            <div key={i} className="autores-card">
              <div className="autores-top">
                <span className="autores-type">{exceptionLabel(exc.exception_type)}</span>
                <span className="autores-resolved"><CheckCircle2 size={13} /> Resolved</span>
              </div>
              {amount && <div className="autores-amount">{fmt(amount)}</div>}
              <div className="autores-reason">{exc.detail || exc.recommended_action || 'Verified by controller'}</div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

// Filter options for the report table
const REPORT_FILTERS = [
  { key: 'all', label: 'All types' },
  { key: 'matched', label: 'Auto reconciled' },
  { key: 'needs_review', label: 'Needs Review' },
  { key: 'auto_resolved', label: 'Auto-resolved' },
  { key: 'phantom_charge', label: 'Phantom Charge' },
  { key: 'ghost_order', label: 'Ghost Order' },
  { key: 'unresolved_settlement', label: 'Unmatched Settlement' },
  { key: 'duplicate_posting', label: 'Duplicate' },
  { key: 'tax_line_mismatch', label: 'Tax Mismatch' },
  { key: 'amount_mismatch', label: 'Amount Mismatch' },
  { key: 'timing_lag', label: 'Timing Lag' },
]

function ReportTable({ matches, exceptions, onSelect, selectedItem }) {
  const [activeFilter, setActiveFilter] = React.useState('all')
  const [searchTerm, setSearchTerm] = React.useState('')

  const matchedReferences = new Set((matches || []).map(m => m.settlement_id))
  const allRows = [
    ...(matches || []).map(match => ({
      kind: 'match',
      data: match,
      type: 'Matched settlement',
      excType: null,
      reference: match.settlement_id,
      amount: match.settled_amount,
      result: match.reason || `Tier ${match.tier || 'match'} match`,
      status: match.status || 'matched',
    })),
    ...(exceptions || [])
      .filter(e => !matchedReferences.has(e.reference_id))
      .map(e => ({
        kind: 'exception',
        data: e,
        type: exceptionLabel(e.exception_type),
        excType: e.exception_type,
        reference: e.reference_id,
        amount: amountFromPaise(e.amount_paise),
        result: e.detail || e.recommended_action,
        status: e.status,
      })),
  ]

  const filterRow = row => {
    if (activeFilter === 'all') return true
    if (activeFilter === 'matched') return row.kind === 'match'
    if (activeFilter === 'needs_review') {
      return row.status === 'needs_human_review' || row.status === 'needs_review'
    }
    if (activeFilter === 'auto_resolved') {
      return row.status === 'auto_resolved' || row.status === 'resolved'
    }
    return row.excType === activeFilter
  }

  const matchesSearch = row => {
    const q = searchTerm.trim().toLowerCase()
    if (!q) return true
    return [
      row.type,
      row.reference,
      row.result,
      row.status,
      row.data?.source,
      row.data?.matched_entry_id,
    ].some(value => String(value || '').toLowerCase().includes(q))
  }

  const rows = allRows.filter(row => filterRow(row) && matchesSearch(row))

  const selectedFilter = REPORT_FILTERS.find(f => f.key === activeFilter) || REPORT_FILTERS[0]

  // Only show filters that have matching rows (except 'all')
  const activeFilters = REPORT_FILTERS.filter(f => {
    if (f.key === 'all') return true
    return allRows.some(row => {
      if (f.key === 'matched') return row.kind === 'match'
      if (f.key === 'needs_review') return row.status === 'needs_human_review' || row.status === 'needs_review'
      if (f.key === 'auto_resolved') return row.status === 'auto_resolved' || row.status === 'resolved'
      return row.excType === f.key
    })
  })

  return (
    <section id="report" className="rd-section rd-report-section">
      <div className="rd-section-header">
        <div>
          <h2 className="rd-section-title">Reconciliation report</h2>
        </div>
        <span className="section-count">{rows.length} records</span>
      </div>

      <div className="rd-report-toolbar">
        <div className="rd-report-search-wrap">
          <Search size={16} className="rd-report-search-icon" />
          <input
            type="text"
            className="rd-report-search-input"
            placeholder="Search settlement, bank reference, or exception"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="rd-report-filter-select-wrap">
          <select
            className="rd-report-filter-select"
            value={activeFilter}
            onChange={e => setActiveFilter(e.target.value)}
          >
            {activeFilters.map(f => (
              <option key={f.key} value={f.key}>{f.label}</option>
            ))}
          </select>
          <ChevronDown size={16} className="rd-report-filter-chevron" />
        </div>
      </div>

      <div className="exc-table-wrap">
        <table className="exc-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Reference</th>
              <th>Amount</th>
              <th>Result</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="rd-filter-empty">No records match this filter.</td>
              </tr>
            )}
            {rows.map((row, index) => {
              const isSelected = selectedItem?.kind === row.kind && (
                row.kind === 'match'
                  ? selectedItem.data.settlement_id === row.reference
                  : selectedItem.data.reference_id === row.reference
              )
              const isMatch = row.kind === 'match'
              return (
                <tr
                  key={`${row.kind}-${row.reference}-${index}`}
                  className={`exc-row ${isSelected ? 'exc-row-selected' : ''}`}
                  onClick={() => onSelect(row)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>
                    <div className={`rd-report-type-pill ${isMatch ? 'rd-report-type-pill-success' : 'rd-report-type-pill-danger'}`}>
                      {row.type}
                    </div>
                  </td>
                  <td><span className="exc-ref">{row.reference || '—'}</span></td>
                  <td><span className="exc-amount">{row.amount != null ? fmt(row.amount) : '—'}</span></td>
                  <td><span className="exc-detail">{row.result || '—'}</span></td>
                  <td><StatusBadge status={row.status} /></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function SettlementDetailsPanel({ item, runData, onClose }) {
  if (!item) return (
    <aside className="rd-settlement-details-panel">
      <div className="rd-settlement-header">
        <h3 className="rd-settlement-title">Settlement Details</h3>
      </div>
      <div className="rd-settlement-empty">
        <Info size={22} color="#64748b" />
        <strong>Select a record</strong>
        <span>Settlement details will appear here when you select a row from the table.</span>
      </div>
    </aside>
  )

  const exception = item.kind === 'exception' ? item.data : null
  const match = item.kind === 'match' ? item.data : runData?.matches?.find(m => m.settlement_id === exception?.reference_id)
  const referenceId = exception?.reference_id || match?.settlement_id
  const amounts = matchAmounts(match, exception?.amount_paise)
  const amount = amounts.expected
  const severity = exception ? severityOf(exception) : 'low'
  const status = exception?.status || match?.status || 'matched'

  return (
    <aside className="rd-settlement-details-panel">
      <div className="rd-settlement-header">
        <h3 className="rd-settlement-title">Settlement Details</h3>
        <button className="rd-settlement-close" onClick={onClose}>
          <X size={18} />
        </button>
      </div>

      <div className="rd-settlement-content">
        <div className="rd-settlement-section">
          <h4 className="rd-settlement-section-title">Record Information</h4>
          <div className="rd-settlement-grid">
            <div className="rd-settlement-item">
              <span className="rd-settlement-label">Type</span>
              <div className="rd-settlement-value">{item.type}</div>
            </div>
            <div className="rd-settlement-item">
              <span className="rd-settlement-label">Reference</span>
              <div className="rd-settlement-value rd-settlement-mono">{referenceId || '—'}</div>
            </div>
            <div className="rd-settlement-item">
              <span className="rd-settlement-label">Amount</span>
              <div className="rd-settlement-value rd-settlement-bold">{amount != null ? fmt(amount) : '—'}</div>
            </div>
            <div className="rd-settlement-item">
              <span className="rd-settlement-label">Status</span>
              <div className="rd-settlement-value"><StatusBadge status={status} /></div>
            </div>
          </div>
        </div>

        {exception && (
          <div className="rd-settlement-section">
            <h4 className="rd-settlement-section-title">Exception Details</h4>
            <div className="rd-settlement-grid">
              <div className="rd-settlement-item">
                <span className="rd-settlement-label">Exception Type</span>
                <div className="rd-settlement-value">{exceptionLabel(exception.exception_type)}</div>
              </div>
              <div className="rd-settlement-item">
                <span className="rd-settlement-label">Severity</span>
                <div className="rd-settlement-value">
                  <span className={`exc-badge ${severity === 'high' ? 'badge-rose' : severity === 'medium' ? 'badge-amber' : 'badge-green'}`}>
                    {severity.charAt(0).toUpperCase() + severity.slice(1)}
                  </span>
                </div>
              </div>
              <div className="rd-settlement-item">
                <span className="rd-settlement-label">Source</span>
                <div className="rd-settlement-value">{exception.source || '—'}</div>
              </div>
            </div>
            {exception.detail && (
              <div className="rd-settlement-detail">
                <span className="rd-settlement-label">Description</span>
                <div className="rd-settlement-value">{exception.detail}</div>
              </div>
            )}
          </div>
        )}

        {match && (
          <div className="rd-settlement-section">
            <h4 className="rd-settlement-section-title">Match Information</h4>
            <div className="rd-settlement-grid">
              <div className="rd-settlement-item">
                <span className="rd-settlement-label">Match Tier</span>
                <div className="rd-settlement-value">{match.tier || '—'}{match.match_subtype ? ` · ${match.match_subtype}` : ''}</div>
              </div>
              <div className="rd-settlement-item">
                <span className="rd-settlement-label">Matched Entry</span>
                <div className="rd-settlement-value rd-settlement-mono">{match.matched_entry_id || '—'}</div>
              </div>
              <div className="rd-settlement-item">
                <span className="rd-settlement-label">Razorpay Amount</span>
                <div className="rd-settlement-value rd-settlement-bold">{amounts.expected != null ? fmt(amounts.expected) : '—'}</div>
              </div>
              <div className="rd-settlement-item">
                <span className="rd-settlement-label">Transferred to Bank</span>
                <div className="rd-settlement-value rd-settlement-bold">{amounts.actual != null ? fmt(amounts.actual) : '—'}</div>
              </div>
              <div className="rd-settlement-item">
                <span className="rd-settlement-label">Difference</span>
                <div className="rd-settlement-value rd-settlement-bold">{amounts.gap != null ? fmt(amounts.gap) : '—'}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}

function InvestigationPanel({ item, runData, onClose }) {
  if (!item) return (
    <aside className="rd-investigation-panel rd-investigation-empty-panel">
      <div className="rd-investigation-header">
        <h3 className="rd-investigation-title">AI Assistant</h3>
        <p className="rd-investigation-subtitle">Investigation workspace</p>
      </div>
      <QueryBox runId={runData?.summary?.run_id} />
    </aside>
  )

  const exception = item.kind === 'exception' ? item.data : null
  const match = item.kind === 'match' ? item.data : runData?.matches?.find(m => m.settlement_id === exception?.reference_id)
  const referenceId = exception?.reference_id || match?.settlement_id
  const amounts = matchAmounts(match, exception?.amount_paise)
  const amount = amounts.expected
  const investigation = exception?.investigation || (runData?.investigations || []).find(i => i.exception_reference_id === referenceId)
  const severity = exception ? severityOf(exception) : 'low'
  const status = exception?.status || match?.status || 'matched'
  const confidence = investigation?.confidence ?? match?.confidence
  const detectedAmount = match ? amounts.actual : null
  const difference = match ? amounts.gap : amount

  return (
    <div className="rd-investigation-panel">
      <div className="rd-investigation-header">
        <div className="rd-investigation-title-row">
          <h3 className="rd-investigation-title">Settlement Details</h3>
          <button className="rd-investigation-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="rd-investigation-badges">
          {exception && <span className={`exc-badge ${severity === 'high' ? 'badge-rose' : severity === 'medium' ? 'badge-amber' : 'badge-green'}`}>
            {severity.charAt(0).toUpperCase() + severity.slice(1)} severity
          </span>}
          <StatusBadge status={status} />
        </div>
      </div>

      <div className="rd-investigation-content">
        {/* Exception Summary */}
        <div className="rd-inv-section">
          <h4 className="rd-inv-section-title">Exception Summary</h4>
          <div className="rd-inv-grid">
            <div className="rd-inv-item">
              <span className="rd-inv-label">Exception Type</span>
              <span className="rd-inv-value">{exception ? exceptionLabel(exception.exception_type) : 'Matched settlement'}</span>
            </div>
            <div className="rd-inv-item">
              <span className="rd-inv-label">Reference ID</span>
              <span className="rd-inv-value rd-inv-mono">{referenceId || '—'}</span>
            </div>
            <div className="rd-inv-item">
              <span className="rd-inv-label">Expected Amount</span>
              <span className="rd-inv-value rd-inv-bold">{amount != null ? fmt(amount) : '—'}</span>
            </div>
            <div className="rd-inv-item">
              <span className="rd-inv-label">Source</span>
              <span className="rd-inv-value">{exception?.source || (match ? 'Bank reconciliation' : '—')}</span>
            </div>
            <div className="rd-inv-item">
              <span className="rd-inv-label">Detected amount</span>
              <span className="rd-inv-value rd-inv-bold">{detectedAmount != null ? fmt(detectedAmount) : '—'}</span>
            </div>
            <div className="rd-inv-item">
              <span className="rd-inv-label">Difference</span>
              <span className="rd-inv-value rd-inv-bold">{difference != null ? fmt(difference) : '—'}</span>
            </div>
            <div className="rd-inv-item">
              <span className="rd-inv-label">Run date</span>
              <span className="rd-inv-value">{formatDate(runData?.summary?.run_at)}</span>
            </div>
          </div>
          {exception?.detail && (
            <div className="rd-inv-detail">
              <span className="rd-inv-label">Description</span>
              <span className="rd-inv-value">{exception.detail}</span>
            </div>
          )}
        </div>

        {/* Evidence Comparison */}
        <div className="rd-inv-section">
          <h4 className="rd-inv-section-title">Evidence Comparison</h4>
          <div className="rd-inv-evidence">
            <div className="rd-inv-evidence-col">
              <div className="rd-inv-evidence-header">Razorpay Settlement</div>
              <div className="rd-inv-evidence-row">
                <span className="rd-inv-e-label">Settlement ID</span>
                <span className="rd-inv-e-value rd-inv-mono">{referenceId}</span>
              </div>
              <div className="rd-inv-evidence-row">
                <span className="rd-inv-e-label">Expected Credit</span>
                <span className="rd-inv-e-value rd-inv-bold">{amount != null ? fmt(amount) : '—'}</span>
              </div>
              <div className="rd-inv-evidence-row">
                <span className="rd-inv-e-label">Source</span>
                <span className="rd-inv-e-value">{exception?.source || 'Bank reconciliation'}</span>
              </div>
            </div>

            <div className="rd-inv-evidence-col">
              <div className="rd-inv-evidence-header">Bank Statement</div>
              {match ? (
                <>
                  <div className="rd-inv-evidence-row">
                    <span className="rd-inv-e-label">Ledger Entry</span>
                    <span className="rd-inv-e-value rd-inv-mono">{match.matched_entry_id || '—'}</span>
                  </div>
                  <div className="rd-inv-evidence-row">
                    <span className="rd-inv-e-label">Transferred to Bank</span>
                    <span className="rd-inv-e-value rd-inv-bold">{amounts.actual != null ? fmt(amounts.actual) : '—'}</span>
                  </div>
                  <div className="rd-inv-evidence-row">
                    <span className="rd-inv-e-label">Difference</span>
                    <span className="rd-inv-e-value rd-inv-bold">{amounts.gap != null ? fmt(amounts.gap) : '—'}</span>
                  </div>
                  <div className="rd-inv-evidence-row">
                    <span className="rd-inv-e-label">Match Tier</span>
                    <span className="rd-inv-e-value">{match.tier != null ? `Tier ${match.tier}${match.match_subtype ? ` · ${match.match_subtype}` : ''}` : '—'}</span>
                  </div>
                </>
              ) : (
                <div className="rd-inv-evidence-empty">
                  <AlertCircle size={16} color="#e11d48" />
                  <span>No corresponding credit found</span>
                </div>
              )}
            </div>

            <div className="rd-inv-evidence-col">
              <div className="rd-inv-evidence-header">Matching Engine</div>
              <div className="rd-inv-evidence-row">
                <span className="rd-inv-e-label">Verdict</span>
                  <span className={`rd-inv-e-value ${exception ? 'rd-inv-red' : ''}`}>{exception ? 'Exception flagged' : 'Matched'}</span>
              </div>
              <div className="rd-inv-evidence-row">
                <span className="rd-inv-e-label">Issue</span>
                  <span className="rd-inv-e-value">{exception?.recommended_action || match?.reason || 'Verified by matching engine'}</span>
              </div>
              {confidence != null && (
                <div className="rd-inv-evidence-row">
                  <span className="rd-inv-e-label">Confidence</span>
                  <span className="rd-inv-e-value rd-inv-bold">{confidence <= 1 ? Math.round(confidence * 100) : Math.round(confidence)}%</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* AI Conclusion */}
        {(investigation?.explanation || match?.reason || exception?.detail) && (
          <div className="rd-inv-section">
            <h4 className="rd-inv-section-title">AI Investigation</h4>
            <div className="rd-inv-ai-box">
              <div className="rd-inv-ai-header">
                <MessageSquare size={14} color="#7c3aed" />
                <span>AI Conclusion</span>
              </div>
              <p className="rd-inv-ai-text">{investigation?.explanation || match?.reason || exception?.detail}</p>
              {confidence != null && (
                <div className="rd-inv-ai-confidence">
                  Confidence: {confidence <= 1 ? Math.round(confidence * 100) : Math.round(confidence)}%
                </div>
              )}
            </div>
          </div>
        )}

        <div className="rd-inv-section">
          <h4 className="rd-inv-section-title">Matching signals</h4>
          <div className="rd-inv-signals">
            {[
              ['Amount', match ? 'Matched' : 'Not matched'],
              ['Reference', match ? 'Matched' : 'Not matched'],
              ['Date window', match ? 'Matched' : 'No credit found'],
              ['Narration / fuzzy', match ? `Tier ${match.tier || 'match'}` : 'Not matched'],
            ].map(([label, value]) => <div className="rd-inv-signal" key={label}><span>{label}</span><strong className={match ? 'rd-inv-signal-ok' : 'rd-inv-signal-fail'}>{value}</strong></div>)}
          </div>
        </div>

        {/* Recommended Action */}
        {exception?.recommended_action && (
          <div className="rd-inv-section">
            <h4 className="rd-inv-section-title">Recommended Action</h4>
            <div className="rd-inv-action-box">
              <p>{exception.recommended_action}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Exception Breakdown strip (Razorpay settlement exceptions only) ── */
const RAZORPAY_EXC_TYPES = {
  unresolved_settlement: { color: '#e8353e', label: 'Unmatched Settlement' },
  amount_mismatch:       { color: '#e05c2b', label: 'Amount Mismatch' },
  timing_lag:            { color: '#f0a500', label: 'Timing Lag' },
  duplicate_posting:     { color: '#6c5ecf', label: 'Duplicate' },
  tax_line_mismatch:     { color: '#0ea5e9', label: 'Tax Mismatch' },
}
const EXC_SEGMENT_ORDER = [
  'unresolved_settlement', 'amount_mismatch', 'timing_lag',
  'duplicate_posting', 'tax_line_mismatch',
]

function ExceptionBreakdown({ exceptions }) {
  const relevant = (exceptions || []).filter(e => e.exception_type in RAZORPAY_EXC_TYPES)
  if (relevant.length === 0) return null

  const counts = relevant.reduce((acc, e) => {
    acc[e.exception_type] = (acc[e.exception_type] || 0) + 1
    return acc
  }, {})
  const total = relevant.length
  const active = EXC_SEGMENT_ORDER.filter(t => counts[t] > 0)

  return (
    <section className="rd-exc-breakdown rd-page-wide">
      <div className="rd-exc-breakdown-header">
        <div>
          <span className="rd-exc-breakdown-title">Exception Breakdown</span>
          <span className="rd-exc-breakdown-scope">Razorpay settlement exceptions only</span>
        </div>
        <span className="rd-exc-total-badge">{total} total</span>
      </div>

      <div className="rd-exc-bar">
        {active.map(type => {
          const cfg = RAZORPAY_EXC_TYPES[type]
          const w = ((counts[type] / total) * 100).toFixed(2)
          return (
            <div
              key={type}
              className="rd-exc-bar-seg"
              style={{ width: `${w}%`, background: cfg.color }}
              title={`${cfg.label}: ${counts[type]}`}
            />
          )
        })}
      </div>

      <div className="rd-exc-legend">
        {active.map(type => {
          const cfg = RAZORPAY_EXC_TYPES[type]
          return (
            <span key={type} className="rd-exc-legend-item">
              <span className="rd-exc-legend-dot" style={{ background: cfg.color }} />
              {cfg.label} ({counts[type]})
            </span>
          )
        })}
      </div>
    </section>
  )
}

export default function RunDetailsPage() {
  const { runId, refId: pathRefId } = useParams()
  const [searchParams] = useSearchParams()
  const refId = pathRefId || searchParams.get('exception')
  const [run, setRun] = useState(null)
  const [accuracy, setAccuracy] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedItem, setSelectedItem] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [runRes, accRes] = await Promise.allSettled([
        axios.get(`${API}/runs/${runId}`),
        axios.get(`${API}/accuracy-report/${runId}`),
      ])
      if (runRes.status === 'fulfilled') setRun(runRes.value.data)
      else throw new Error('Run not found')
      if (accRes.status === 'fulfilled') setAccuracy(accRes.value.data)
    } catch (e) {
      setError(e.message || 'Failed to load reconciliation results')
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => { load() }, [load])

  // Auto-select exception if refId is in URL
  useEffect(() => {
    if (refId && run?.exceptions) {
      const exception = run.exceptions.find(e => e.reference_id === refId)
      const match = run.matches?.find(m => m.settlement_id === refId)
      if (exception) setSelectedItem({ kind: 'exception', data: exception })
      else if (match) setSelectedItem({ kind: 'match', data: match })
    }
  }, [refId, run])

  if (loading) return (
    <div className="rd-state-wrap">
      <div className="rd-spinner" />
      <p className="rd-state-text">Loading reconciliation results…</p>
    </div>
  )

  if (error || !run) return (
    <div className="rd-state-wrap">
      <AlertCircle size={32} color="#e11d48" />
      <p className="rd-state-text">{error || "Couldn't load this reconciliation."}</p>
      <div className="rd-state-actions">
        <button className="btn-primary" onClick={load}>Try again</button>
        <Link to="/" className="btn-secondary-outline">Back to Overview</Link>
      </div>
    </div>
  )

  const s = run.summary || {}
  const exceptions = run.exceptions || []
  const matches = run.matches || []
  const totalRec = s.total_settlement_batches ?? 0
  const matched = s.matched_batches || 0
  const matchRate = s.match_rate_pct || 0

  const unmatched = Math.max(totalRec - matched, 0)

  return (
    <div className="rd-page rd-page-split">
      <div className="rd-main-content">
      {/* Header */}
      <div className="rd-header-row">
        <div className="rd-header-left">
          <div className="rd-breadcrumb">
            <Link to="/reconciliations" className="rd-breadcrumb-link"><ArrowLeft size={13} /> Reconciliations</Link>
          </div>
          <div className="rd-title-row">
            <h1 className="rd-page-title">Reconciliation Run {runLabel(runId)}</h1>
            <span className="rd-status-badge"><CheckCircle2 size={13} /> Completed</span>
          </div>
          <p className="rd-page-subtitle">Settlement and bank records have been reconciled.</p>
        </div>
        <div className="rd-header-right">
          <span className="rd-run-date"><Clock size={13} /> {formatDate(s.run_at)}</span>
          <Link to="/reconciliations" className="btn-secondary-outline">Back to Reconciliations</Link>
          <button className="btn-secondary-outline" disabled style={{ opacity: 0.5, cursor: 'not-allowed' }}>
            <Download size={14} /> Export Report
          </button>
        </div>
      </div>

      {/* Match rate hero */}
      <section className="rd-hero-section rd-page-wide">
        <div className="rd-hero-left">
          <MatchRateRing rate={matchRate} />
          <div>
            <div className="rd-hero-label">Match Rate</div>
            <div className="rd-hero-sub">{matched} of {totalRec} records matched</div>
          </div>
        </div>
        <div className="rd-hero-kpis">
          <KpiCard label="Settlements Checked" value={totalRec} icon={Activity} color="#1e56a0" sub="Razorpay settlements" />
          <KpiCard label="Reached Bank" value={matched} icon={CheckCircle2} color="#059669" sub={`${pct(matchRate)} match rate`} />
          <KpiCard label="Could Not Confirm" value={unmatched} icon={AlertTriangle} color="#d97706" sub="need investigation" />
          <KpiCard label="Match Rate" value={pct(matchRate)} icon={AlertCircle} color="#7c3aed" sub="settlement to bank" />
        </div>
      </section>

      {/* Exception Breakdown — Razorpay settlement exceptions only */}
      <ExceptionBreakdown exceptions={exceptions} />

      {/* Unified report table */}
      <div className="rd-report-workspace">
        <div className="rd-left-block">
          {selectedItem ? (
            <InvestigationPanel
              item={selectedItem}
              runData={run}
              onClose={() => setSelectedItem(null)}
            />
          ) : (
            <ReportTable
              matches={matches}
              exceptions={exceptions}
              onSelect={item => setSelectedItem(item)}
              selectedItem={selectedItem}
            />
          )}
        </div>
        <InvestigationPanel
          item={null}
          runData={run}
        />
      </div>

      </div>

    </div>
  )
}