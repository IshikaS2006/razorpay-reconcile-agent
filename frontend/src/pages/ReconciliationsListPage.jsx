import React, { useEffect, useState, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import axios from 'axios'
import {
  Plus, Search, SlidersHorizontal, ChevronRight, ChevronLeft,
  FileSpreadsheet, TrendingUp, AlertTriangle, Clock, BarChart3,
  CheckCircle2, XCircle, ExternalLink, Info, MoreHorizontal
} from 'lucide-react'

const API = 'http://127.0.0.1:8000'



function fmt(n, prefix = '') {
  if (n == null) return '—'
  return prefix + Number(n).toLocaleString('en-IN')
}
function fmtPct(v) {
  if (v == null) return '—'
  return Number(v).toFixed(1) + '%'
}
function fmtTime(s) {
  if (s == null) return '—'
  return Number(s).toFixed(1) + 's'
}
function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return {
    date: d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }),
    time: d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })
  }
}
function runLabel(id) {
  return 'Run #' + String(id).padStart(3, '0')
}
function runTag(id, run_at) {
  if (!run_at) return `run_${String(id).padStart(3, '0')}`
  const d = new Date(run_at)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `run_${y}${m}${day}_${String(id).padStart(3, '0')}`
}

function StatusChip({ status }) {
  if (status === 'completed' || status === 'Completed') {
    return <span className="rl-status-chip rl-chip-completed"><CheckCircle2 size={11} /> Completed</span>
  }
  if (status === 'failed' || status === 'Failed') {
    return <span className="rl-status-chip rl-chip-failed"><XCircle size={11} /> Failed</span>
  }
  return <span className="rl-status-chip rl-chip-pending"><Clock size={11} /> {status}</span>
}

function MatchBar({ rate }) {
  if (rate == null) return <span className="rl-dash">—</span>
  const color = rate >= 93 ? '#059669' : rate >= 88 ? '#d97706' : '#e11d48'
  return (
    <div className="rl-match-bar-wrap">
      <span className="rl-match-rate-val" style={{ color }}>{fmtPct(rate)}</span>
      <div className="rl-match-bar">
        <div className="rl-match-bar-fill" style={{ width: `${Math.min(rate, 100)}%`, background: color }} />
      </div>
    </div>
  )
}

function SummaryCard({ icon: Icon, iconColor, iconBg, label, value, sub }) {
  return (
    <div className="rl-summary-card">
      <div className="rl-summary-icon" style={{ background: iconBg, color: iconColor }}>
        <Icon size={16} />
      </div>
      <div className="rl-summary-body">
        <div className="rl-summary-label">{label}</div>
        <div className="rl-summary-value">{value}</div>
        <div className="rl-summary-sub">{sub}</div>
      </div>
    </div>
  )
}

const PAGE_SIZE = 8

export default function ReconciliationsListPage() {
  const navigate = useNavigate()
  const [liveRuns, setLiveRuns] = useState([])
  const [loading, setLoading] = useState(true)

  // filters
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [page, setPage] = useState(1)

  useEffect(() => {
    axios.get(`${API}/runs`)
      .then(r => setLiveRuns(r.data || []))
      .catch(() => setLiveRuns([]))
      .finally(() => setLoading(false))
  }, [])

  const allRuns = useMemo(() => {
    return liveRuns.map(r => ({
      run_id: r.run_id,
      label: runLabel(r.run_id),
      run_id_tag: runTag(r.run_id, r.run_at),
      period: r.run_at ? fmtDate(r.run_at).date : '—',
      status: 'completed',
      records: r.total_settlement_batches ?? 0,
      matched: r.matched_batches ?? 0,
      match_rate_pct: r.match_rate_pct,
      exceptions: r.total_exceptions ?? 0,
      total_time_sec: r.total_time_sec,
      run_at: r.run_at,
    })).sort((a, b) => b.run_id - a.run_id)
  }, [liveRuns])

  // Aggregate summary stats
  const totalRuns = allRuns.length
  const totalRecords = allRuns.reduce((acc, r) => acc + (r.records || 0), 0)
  const completedRuns = allRuns.filter(r => r.status === 'completed')
  const avgMatch = completedRuns.length > 0
    ? (completedRuns.reduce((a, r) => a + (r.match_rate_pct || 0), 0) / completedRuns.length)
    : 0
  const openExceptions = allRuns.reduce((acc, r) => acc + (r.exceptions || 0), 0)
  const completedWithTime = completedRuns.filter(r => r.total_time_sec != null)
  const avgTime = completedWithTime.length > 0
    ? (completedWithTime.reduce((a, r) => a + r.total_time_sec, 0) / completedWithTime.length)
    : 0

  // Filtered rows
  const filtered = useMemo(() => {
    return allRuns.filter(r => {
      const q = search.toLowerCase()
      const matchSearch = !q ||
        r.label.toLowerCase().includes(q) ||
        (r.run_id_tag || '').toLowerCase().includes(q) ||
        String(r.run_id).includes(q)
      const matchStatus = statusFilter === 'all' || r.status === statusFilter
      return matchSearch && matchStatus
    })
  }, [allRuns, search, statusFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const handleSearch = (e) => { setSearch(e.target.value); setPage(1) }
  const handleStatus = (e) => { setStatusFilter(e.target.value); setPage(1) }

  return (
    <div className="rl-page">
      {/* ── Header ── */}
      <div className="rl-header-row">
        <div>
          <h1 className="rl-page-title">Reconciliations</h1>
          <p className="rl-page-subtitle">View and manage all your reconciliation runs.</p>
        </div>
        <button className="btn-primary" onClick={() => navigate('/reconciliations/new')}>
          <Plus size={15} /> New Reconciliation
        </button>
      </div>

      {/* ── Summary KPI cards ── */}
      <div className="rl-summary-row">
        <SummaryCard icon={FileSpreadsheet} iconColor="#1e56a0" iconBg="#dbeafe"
          label="Total Runs" value={loading ? '…' : totalRuns} sub="All time" />
        <SummaryCard icon={BarChart3} iconColor="#059669" iconBg="#d1fae5"
          label="Records Processed" value={loading ? '…' : fmt(totalRecords)} sub="Across all runs" />
        <SummaryCard icon={TrendingUp} iconColor="#7c3aed" iconBg="#ede9fe"
          label="Avg. Match Rate" value={loading ? '…' : fmtPct(avgMatch)} sub="Across all runs" />
        <SummaryCard icon={AlertTriangle} iconColor="#d97706" iconBg="#fef3c7"
          label="Open Exceptions" value={loading ? '…' : openExceptions} sub="Across all runs" />
        <SummaryCard icon={Clock} iconColor="#0ea5e9" iconBg="#e0f2fe"
          label="Avg. Processing Time" value={loading ? '…' : fmtTime(avgTime)} sub="Per run" />
      </div>

      {/* ── Search / filters ── */}
      <div className="rl-filters-row">
        <div className="rl-search-wrap">
          <Search size={14} className="rl-search-icon" />
          <input
            className="rl-search-input"
            placeholder="Search by run name or run ID..."
            value={search}
            onChange={handleSearch}
          />
        </div>
        <select className="rl-filter-select" value={statusFilter} onChange={handleStatus}>
          <option value="all">All statuses</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
        </select>
        <button className="rl-filter-btn">
          <SlidersHorizontal size={14} /> Filters
        </button>
      </div>

      {/* ── Table ── */}
      <div className="rl-table-wrap">
        <table className="rl-table">
          <thead>
            <tr>
              <th>Run</th>
              <th>Period</th>
              <th>Status</th>
              <th className="rl-th-right">Records</th>
              <th className="rl-th-right">Matched</th>
              <th className="rl-th-right">Exceptions</th>
              <th>Match Rate</th>
              <th className="rl-th-right">Processing Time</th>
              <th>Created At</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={10} className="rl-td-loading">Loading runs…</td></tr>
            ) : pageRows.length === 0 ? (
              <tr><td colSpan={10} className="rl-td-loading">No runs found.</td></tr>
            ) : pageRows.map(row => {
              const d = fmtDate(row.run_at)
              const isCompleted = true
              const excColor = !row.exceptions ? 'var(--text-muted)' : row.exceptions >= 6 ? '#be123c' : '#d97706'
              return (
                <tr key={row.run_id} className="rl-row" onClick={() => isCompleted && navigate(`/reconciliations/${row.run_id}`)}>
                  <td>
                    <div className="rl-run-label">{row.label}</div>
                    <div className="rl-run-tag">{row.run_id_tag}</div>
                  </td>
                  <td className="rl-period">{row.period}</td>
                  <td><StatusChip status={row.status} /></td>
                  <td className="rl-td-right">
                    <span className="rl-num">{row.records}</span>
                    <span className="rl-num-sub">Records</span>
                  </td>
                  <td className="rl-td-right">
                    {row.matched != null ? (
                      <>
                        <span className="rl-num">{row.matched}</span>
                        <span className="rl-num-sub">({fmtPct(row.match_rate_pct)})</span>
                      </>
                    ) : <span className="rl-dash">—</span>}
                  </td>
                  <td className="rl-td-right">
                    {row.exceptions != null ? (
                      <>
                        <span className="rl-num" style={{ color: excColor }}>{row.exceptions}</span>
                        <span className="rl-num-sub" style={{ color: excColor }}>Needs review</span>
                      </>
                    ) : <span className="rl-dash">—</span>}
                  </td>
                  <td><MatchBar rate={row.match_rate_pct} /></td>
                  <td className="rl-td-right">
                    <span className="rl-num">{fmtTime(row.total_time_sec)}</span>
                  </td>
                  <td>
                    <div className="rl-date">{d.date}</div>
                    <div className="rl-time">{d.time}</div>
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    {isCompleted ? (
                      <Link to={`/reconciliations/${row.run_id}`} className="rl-view-btn">
                        View Results
                      </Link>
                    ) : (
                      <span className="rl-dash rl-view-disabled">View Details</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {/* ── Pagination ── */}
        <div className="rl-pagination-row">
          <span className="rl-pagination-info">
            Showing {Math.min((page - 1) * PAGE_SIZE + 1, filtered.length)}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length} runs
          </span>
          <div className="rl-pagination-btns">
            <button className="rl-page-btn" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
              <ChevronLeft size={14} />
            </button>
            {Array.from({ length: Math.min(totalPages, 4) }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                className={`rl-page-btn rl-page-num ${page === p ? 'rl-page-active' : ''}`}
                onClick={() => setPage(p)}
              >{p}</button>
            ))}
            {totalPages > 4 && <span className="rl-page-ellipsis">…</span>}
            {totalPages > 4 && (
              <button
                className={`rl-page-btn rl-page-num ${page === totalPages ? 'rl-page-active' : ''}`}
                onClick={() => setPage(totalPages)}
              >{totalPages}</button>
            )}
            <button className="rl-page-btn" disabled={page === totalPages} onClick={() => setPage(p => p + 1)}>
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* ── Info card ── */}
      <div className="rl-info-card">
        <Info size={15} color="#0ea5e9" style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          <div className="rl-info-title">What is a reconciliation run?</div>
          <div className="rl-info-sub">Each run matches your Razorpay settlements with bank statement credits to identify matches, exceptions, and cash impact.</div>
        </div>
        <a href="https://razorpay.com/docs/" target="_blank" rel="noreferrer" className="rl-info-link">
          Learn more <ExternalLink size={11} />
        </a>
      </div>
    </div>
  )
}
