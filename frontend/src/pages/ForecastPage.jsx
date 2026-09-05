import React, { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import {
  TrendingUp, ChevronDown, RefreshCw, ArrowUpRight, ArrowDownRight,
  Info, CheckCircle2, Clock, ArrowDown, ArrowUp, ExternalLink
} from 'lucide-react'

const API = 'http://127.0.0.1:8000'

/* ── formatters ─────────────────────────────────────────────── */
function inr(paise) {
  if (paise == null || isNaN(paise)) return '—'
  return '₹' + (paise / 100).toLocaleString('en-IN', {
    minimumFractionDigits: 0, maximumFractionDigits: 0
  })
}
function inrFull(paise) {
  if (paise == null || isNaN(paise)) return '—'
  return '₹' + (paise / 100).toLocaleString('en-IN', {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  })
}
function pct(v, digits = 1) {
  if (v == null || isNaN(v)) return '—'
  return `${Number(v).toFixed(digits)}%`
}
function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric'
  })
}

/* ── SVG bar chart ──────────────────────────────────────────── */
function ForecastBarChart({ forecast }) {
  if (!forecast || forecast.length === 0) return (
    <div className="fcp-chart-empty">No forecast data available</div>
  )

  const W = 640, H = 200, PAD_L = 56, PAD_B = 28, PAD_T = 12, PAD_R = 16
  const chartW = W - PAD_L - PAD_R
  const chartH = H - PAD_T - PAD_B

  // Use projected_cash_paise for the line, inflow bars for confirmed/projected split
  const maxVal = Math.max(...forecast.map(f => f.projected_cash_paise), 1)
  // Nice round ceiling for Y axis
  const magnitude = Math.pow(10, Math.floor(Math.log10(maxVal)))
  const yMax = Math.ceil(maxVal / magnitude) * magnitude

  const barW = Math.min(48, (chartW / forecast.length) * 0.55)
  const gap = chartW / forecast.length

  // Y grid lines — 4 ticks
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(t => ({
    y: PAD_T + chartH - t * chartH,
    label: inr(yMax * t)
  }))

  // Points for cumulative projected cash line
  const linePoints = forecast.map((f, i) => {
    const x = PAD_L + gap * i + gap / 2
    const y = PAD_T + chartH - (f.projected_cash_paise / yMax) * chartH
    return `${x},${y}`
  }).join(' ')

  // Area under the line
  const firstX = PAD_L + gap / 2
  const lastX = PAD_L + gap * (forecast.length - 1) + gap / 2
  const areaPoints = [
    `${firstX},${PAD_T + chartH}`,
    ...forecast.map((f, i) => {
      const x = PAD_L + gap * i + gap / 2
      const y = PAD_T + chartH - (f.projected_cash_paise / yMax) * chartH
      return `${x},${y}`
    }),
    `${lastX},${PAD_T + chartH}`
  ].join(' ')

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="fcp-chart-svg" aria-label="Cash forecast chart">
      {/* Grid lines */}
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={PAD_L} y1={t.y} x2={W - PAD_R} y2={t.y}
            stroke="#e2e8f0" strokeWidth="1" />
          <text x={PAD_L - 6} y={t.y + 4} fontSize="9" fill="#94a3b8"
            textAnchor="end">{t.label}</text>
        </g>
      ))}

      {/* Area fill under line */}
      <polygon points={areaPoints} fill="#1d4ed8" fillOpacity="0.06" />

      {/* Inflow bars: confirmed (green) + projected (blue-gray) stacked */}
      {forecast.map((f, i) => {
        const x = PAD_L + gap * i + gap / 2 - barW / 2
        const confirmed = f.confirmed_inflow_paise ?? f.expected_inflow_paise ?? 0
        const projected = Math.max(0, (f.expected_inflow_paise ?? 0) - confirmed)
        const confirmedH = (confirmed / yMax) * chartH
        const projectedH = (projected / yMax) * chartH
        const baseY = PAD_T + chartH
        return (
          <g key={i}>
            {/* Confirmed (green) */}
            {confirmedH > 0 && (
              <rect x={x} y={baseY - confirmedH} width={barW} height={confirmedH}
                fill="#10b981" fillOpacity="0.75" rx="2" />
            )}
            {/* Projected (blue) stacked on top */}
            {projectedH > 0 && (
              <rect x={x} y={baseY - confirmedH - projectedH} width={barW} height={projectedH}
                fill="#3b82f6" fillOpacity="0.5" rx="2" />
            )}
            {/* X label */}
            <text x={PAD_L + gap * i + gap / 2} y={H - 6} fontSize="9"
              fill="#64748b" textAnchor="middle">
              {f.period === 'today' ? 'Today' : f.period}
            </text>
          </g>
        )
      })}

      {/* Projected cash line */}
      <polyline points={linePoints} fill="none" stroke="#1d4ed8"
        strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

      {/* Dots on line */}
      {forecast.map((f, i) => {
        const x = PAD_L + gap * i + gap / 2
        const y = PAD_T + chartH - (f.projected_cash_paise / yMax) * chartH
        return <circle key={i} cx={x} cy={y} r="4" fill="#1d4ed8" stroke="#fff" strokeWidth="1.5" />
      })}
    </svg>
  )
}



/* ── Main page ──────────────────────────────────────────────── */
export default function ForecastPage() {
  const [runs, setRuns]                 = useState([])
  const [selectedRunId, setSelectedRunId] = useState(null)
  const [timeseries, setTimeseries]     = useState(null)   // /cash-forecast/timeseries
  const [cashPos, setCashPos]           = useState(null)   // /forecast (cash position)
  const [loading, setLoading]           = useState(true)
  const [error, setError]               = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)

  /* ── load run list ── */
  const fetchRuns = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/runs`, { timeout: 5000 })
      const list = res.data || []
      setRuns(list)
      if (list.length > 0) setSelectedRunId(list[0].run_id)
    } catch {
      setError('Could not reach the backend. Make sure the server is running.')
      setLoading(false)
    }
  }, [])

  /* ── load data for selected run ── */
  const fetchData = useCallback(async (runId) => {
    if (!runId) return
    setLoading(true)
    setError('')
    try {
      const [tsRes, posRes] = await Promise.allSettled([
        axios.get(`${API}/cash-forecast/timeseries/${runId}`, { timeout: 5000 }),
        axios.get(`${API}/forecast/${runId}`,                 { timeout: 5000 }),
      ])
      if (tsRes.status  === 'fulfilled') setTimeseries(tsRes.value.data)
      if (posRes.status === 'fulfilled') setCashPos(posRes.value.data)
    } catch {
      setError('Failed to load forecast data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchRuns() }, [fetchRuns])
  useEffect(() => { if (selectedRunId) fetchData(selectedRunId) }, [selectedRunId, fetchData])

  /* ── derived values ── */
  const forecast          = timeseries?.forecast ?? []
  const confirmedCash     = timeseries?.confirmed_cash_paise ?? timeseries?.current_cash_paise ?? 0
  const atRisk            = timeseries?.at_risk_cash_paise ?? cashPos?.at_risk_total ?? 0
  const confirmedInflows  = timeseries?.inflow_rows?.confirmed ?? []
  const projectedInflows  = timeseries?.inflow_rows?.projected ?? []
  const outflowRows       = timeseries?.outflow_rows ?? []
  const accuracy          = timeseries?.backtest ?? null
  const identityCheck     = timeseries?.identity_check ?? null
  const growthCheck       = timeseries?.growth_check ?? null

  // Period extremes
  const lastPeriod        = forecast[forecast.length - 1]
  const projectedEnd      = lastPeriod?.projected_cash_paise ?? 0
  const totalInflow       = timeseries?.expected_inflow_paise ?? lastPeriod?.cumulative_inflows_paise ?? 0
  const totalOutflow      = lastPeriod?.cumulative_outflows_paise ?? lastPeriod?.expected_outflow_paise ?? 0

  // Trend vs opening
  const changePct = confirmedCash > 0
    ? ((projectedEnd - confirmedCash) / confirmedCash) * 100
    : 0
  const trendUp = changePct >= 0

  const runLabel = runs.find(r => r.run_id === selectedRunId)
  const runStr   = runLabel ? `Run #${runLabel.run_id}` : '—'

  return (
    <div className="fcp-page">
      {/* ── Header ── */}
      <header className="fcp-header">
        <div className="fcp-header-left">
          <div className="fcp-title-row">
            <TrendingUp size={20} className="fcp-title-icon" strokeWidth={2} />
            <h1>Forecast</h1>
            {selectedRunId && (
              <Link to={`/reconciliations/${selectedRunId}`} className="metrics-view-report-btn">
                <ExternalLink size={13} />
                View report
              </Link>
            )}
          </div>
          <p className="fcp-subtitle">Forward-looking cash projection from Razorpay settlements</p>
        </div>

        {/* Run selector */}
        <div className="fcp-run-selector">
          <button
            type="button"
            className="fcp-run-btn"
            onClick={() => setDropdownOpen(o => !o)}
          >
            <span>{runStr}</span>
            <ChevronDown size={14} />
          </button>
          {dropdownOpen && runs.length > 0 && (
            <ul className="fcp-run-dropdown">
              {runs.map(r => (
                <li
                  key={r.run_id}
                  className={`fcp-run-option ${r.run_id === selectedRunId ? 'active' : ''}`}
                  onClick={() => { setSelectedRunId(r.run_id); setDropdownOpen(false) }}
                >
                  Run #{r.run_id}
                  {r.run_at && (
                    <span className="fcp-run-date">
                      {new Date(r.run_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </header>

      {/* ── Error ── */}
      {error && (
        <div className="fcp-error" role="alert">
          {error}
          <button type="button" className="fcp-retry" onClick={() => fetchData(selectedRunId)}>
            <RefreshCw size={13} /> Retry
          </button>
        </div>
      )}

      {/* ── Skeleton ── */}
      {loading && !error && (
        <div className="fcp-skeleton-wrap">
          <div className="fcp-skeleton-kpi-row">
            {[1,2,3,4].map(i => <div key={i} className="fcp-skeleton-kpi" />)}
          </div>
          <div className="fcp-skeleton-chart" />
        </div>
      )}

      {!loading && !error && (
        <>
          {/* ── KPI row ── */}
          <div className="fcp-kpi-row">
            <KpiCard
              label="Confirmed Cash"
              value={inr(confirmedCash)}
              sub="Settled & reconciled"
              accent="green"
              icon={<CheckCircle2 size={15} />}
            />
            <KpiCard
              label={`Projected (${lastPeriod?.period ?? '—'})`}
              value={inr(projectedEnd)}
              sub={
                <span className={trendUp ? 'fcp-trend-up' : 'fcp-trend-down'}>
                  {trendUp ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                  {pct(Math.abs(changePct))} vs opening
                </span>
              }
              accent="blue"
              icon={<TrendingUp size={15} />}
            />

          </div>

          {/* ── Main two-column layout ── */}
          <div className="fcp-body">
            {/* LEFT: chart + accuracy + inflows table */}
            <div className="fcp-main">

              {/* Chart card */}
              <div className="fcp-card">
                <div className="fcp-card-head">
                  <h2 className="fcp-card-title">Cash Projection</h2>
                  <div className="fcp-chart-legend">
                    <span className="fcp-legend-item">
                      <span className="fcp-legend-dot" style={{ background: '#10b981' }} />
                      Confirmed inflow
                    </span>
                    <span className="fcp-legend-item">
                      <span className="fcp-legend-dot" style={{ background: '#3b82f6' }} />
                      Projected inflow
                    </span>
                    <span className="fcp-legend-item">
                      <span className="fcp-legend-line" />
                      Net cash position
                    </span>
                  </div>
                </div>
                <ForecastBarChart forecast={forecast} />
                <div className="fcp-chart-note">
                  <Info size={12} />
                  Confirmed = already matched settlements awaiting credit.
                  Projected = based on historical settlement patterns.
                </div>
              </div>

              {/* Forecast accuracy card */}
              {accuracy && (
                <div className="fcp-card">
                  <div className="fcp-card-head">
                    <h2 className="fcp-card-title">Forecast Accuracy</h2>
                    <div className="fcp-accuracy-badges">
                      <span className="fcp-accuracy-badge fcp-badge-mape">
                        MAPE {pct(accuracy.mape)}
                      </span>
                      <span className="fcp-accuracy-badge fcp-badge-mae">
                        MAE {inr(accuracy.mae)}
                      </span>
                    </div>
                  </div>
                  <p className="fcp-accuracy-desc">
                    Holdout backtest on recent matched settlements. Lower error means the
                    simple moving-average projection is tracking realized cash more closely.
                  </p>
                  <table className="fcp-acc-table">
                    <thead>
                      <tr>
                        <th>Period</th>
                        <th>Projected</th>
                        <th>Realized</th>
                        <th>Abs error</th>
                        <th>Error %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {accuracy.pairs.map((p, i) => (
                        <tr key={i}>
                          <td className="fcp-acc-period">{p.period}</td>
                          <td>{inr(p.predicted)}</td>
                          <td>{inr(p.actual)}</td>
                          <td>{inr(p.absErr)}</td>
                          <td>
                            <span className={`fcp-err-pct ${p.pctErr <= 5 ? 'fcp-err-good' : p.pctErr <= 15 ? 'fcp-err-ok' : 'fcp-err-bad'}`}>
                              {pct(p.pctErr)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Confirmed inflows table */}
              {confirmedInflows.length > 0 && (
                <div className="fcp-card">
                  <div className="fcp-card-head">
                    <h2 className="fcp-card-title">
                      <ArrowDown size={15} className="fcp-title-check" />
                      Upcoming Inflows — Confirmed
                    </h2>
                    <span className="fcp-count-badge">{confirmedInflows.length} settlements</span>
                  </div>
                  <InflowTable rows={confirmedInflows} kind="confirmed" />
                </div>
              )}

              {/* Projected inflows table */}
              {projectedInflows.length > 0 && (
                <div className="fcp-card">
                  <div className="fcp-card-head">
                    <h2 className="fcp-card-title">
                      <ArrowDown size={15} className="fcp-title-clock" />
                      Upcoming Inflows — Projected
                    </h2>
                    <span className="fcp-count-badge fcp-badge-projected">{projectedInflows.length} windows</span>
                  </div>
                  <InflowTable rows={projectedInflows} kind="projected" />
                </div>
              )}

              {/* Outflows table */}
              {outflowRows.length > 0 && (
                <OutflowsCard rows={outflowRows} />
              )}
            </div>

            {/* RIGHT: summary panel */}
            <aside className="fcp-aside">
              <div className="fcp-card">
                <h2 className="fcp-card-title">Forecast Summary</h2>
                <div className="fcp-summary-rows">
                  <SummaryRow label="Opening Cash"   value={inr(confirmedCash)} />
                  <SummaryRow label="Total Inflows"  value={inr(totalInflow)}   valueClass="fcp-green" />
                  <SummaryRow label="Total Outflows" value={inr(totalOutflow)}  valueClass="fcp-red" />
                  <SummaryRow label="At-risk Cash"   value={inr(atRisk)}        valueClass="fcp-amber" />
                  <div className="fcp-summary-divider" />
                  <SummaryRow label="Closing Cash"   value={inr(projectedEnd)}  valueClass="fcp-blue" bold />
                </div>

                {/* Period breakdown */}
                {forecast.length > 0 && (
                  <div className="fcp-period-table">
                    <div className="fcp-period-head">Period breakdown</div>
                    {forecast.map((f, i) => (
                      <div key={i} className="fcp-period-row">
                        <div>
                          <span className="fcp-period-label">
                            {f.period === 'today' ? 'Today' : f.period}
                          </span>
                          <div className="fcp-chart-note">
                            <Info size={11} />
                            {`${inr(confirmedCash)} + ${inr(f.cumulative_inflows_paise ?? 0)} − ${inr(f.cumulative_outflows_paise ?? 0)}`}
                          </div>
                        </div>
                        <span className="fcp-period-val">{inr(f.projected_cash_paise)}</span>
                      </div>
                    ))}
                  </div>
                )}

                {identityCheck && !identityCheck.ok && (
                  <div className="fcp-chart-note" style={{ color: '#b91c1c' }}>
                    <Info size={12} />
                    Forecast identity check failed. Review backend logs for period-level mismatch details.
                  </div>
                )}

                {growthCheck?.warning && (
                  <div className="fcp-chart-note" style={{ color: '#b45309' }}>
                    <Info size={12} />
                    30-day projected growth of {pct(growthCheck.growth_pct, 2)} exceeds the
                    sanity threshold of {pct(growthCheck.threshold_pct, 0)}.
                  </div>
                )}
              </div>

              {/* Accuracy summary if available */}
              {accuracy && (
                <div className="fcp-card fcp-card-accuracy-aside">
                  <h2 className="fcp-card-title">Model Accuracy</h2>
                  <div className="fcp-accuracy-meter">
                    <div className="fcp-meter-label">
                      <span>MAPE</span>
                      <strong className={accuracy.mape <= 5 ? 'fcp-green' : accuracy.mape <= 15 ? 'fcp-amber' : 'fcp-red'}>
                        {pct(accuracy.mape)}
                      </strong>
                    </div>
                    <div className="fcp-meter-track">
                      <div
                        className="fcp-meter-fill"
                        style={{
                          width: `${Math.min(100, accuracy.mape)}%`,
                          background: accuracy.mape <= 5 ? '#10b981'
                            : accuracy.mape <= 15 ? '#f59e0b'
                            : '#ef4444'
                        }}
                      />
                    </div>
                    <div className="fcp-meter-scale">
                      <span>0%</span><span>Good ≤5%</span><span>100%</span>
                    </div>
                  </div>
                  <div className="fcp-accuracy-note">
                    <Info size={12} />
                    Based on backend holdout backtesting, not a frontend-derived estimate.
                  </div>
                </div>
              )}
            </aside>
          </div>
        </>
      )}

      {/* overlay to close dropdown */}
      {dropdownOpen && (
        <div className="fcp-dropdown-overlay" onClick={() => setDropdownOpen(false)} />
      )}
    </div>
  )
}

/* ── Sub-components ──────────────────────────────────────────── */
function OutflowsCard({ rows }) {
  const visible = rows.slice(0, 8)
  const hidden = rows.length - visible.length

  if (visible.length === 0) return null

  return (
    <div className="fcp-card">
      <div className="fcp-card-head">
        <h2 className="fcp-card-title">
          <ArrowUp size={15} className="fcp-title-outflow" />
          Upcoming Outflows
        </h2>
        <span className="fcp-count-badge fcp-badge-outflow">{rows.length} items</span>
      </div>
      <table className="fcp-inflow-table">
        <thead>
          <tr>
            <th>Expected Date</th>
            <th>Type</th>
            <th>Description</th>
            <th>Amount</th>
            <th>Probability</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((r, i) => (
            <tr key={i}>
              <td className="fcp-date-cell">{fmtDate(r.expected_date)}</td>
              <td className="fcp-source-cell">{r.type}</td>
              <td className="fcp-desc-cell">{r.description}</td>
              <td className="fcp-amount-red">{inrFull(r.amount_paise)}</td>
              <td>
                <span className={`fcp-prob-badge ${r.probability_pct === 100 ? 'fcp-prob-100' : 'fcp-prob-90'}`}>
                  {r.probability_pct}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hidden > 0 && (
        <div className="fcp-table-more">+{hidden} more outflows not shown</div>
      )}
    </div>
  )
}

function KpiCard({ label, value, sub, accent, icon }) {
  return (
    <div className={`fcp-kpi fcp-kpi-${accent}`}>
      <div className="fcp-kpi-top">
        <span className={`fcp-kpi-icon fcp-icon-${accent}`}>{icon}</span>
        <span className="fcp-kpi-label">{label}</span>
      </div>
      <div className="fcp-kpi-val">{value}</div>
      <div className="fcp-kpi-sub">{sub}</div>
    </div>
  )
}

function SummaryRow({ label, value, valueClass = '', bold = false }) {
  return (
    <div className="fcp-summary-row">
      <span className="fcp-summary-label">{label}</span>
      <span className={`fcp-summary-val ${valueClass} ${bold ? 'fcp-bold' : ''}`}>{value}</span>
    </div>
  )
}

function InflowTable({ rows, kind }) {
  const visible = rows.slice(0, 8)
  const hidden  = rows.length - visible.length

  return (
    <>
      <table className="fcp-inflow-table">
        <thead>
          <tr>
            <th>Expected Date</th>
            <th>Source</th>
            <th>Description</th>
            <th>Amount</th>
            <th>Probability</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((m, i) => {
            const probability = kind === 'confirmed' ? 100 : (m.probability_pct ?? 90)
            return (
              <tr key={i}>
                <td className="fcp-date-cell">{fmtDate(m.expected_date)}</td>
                <td className="fcp-source-cell">{m.source || 'Razorpay'}</td>
                <td className="fcp-desc-cell">
                  {m.description || `Settlement (${m.settlement_id || `#${i + 1}`})`}
                </td>
                <td className={kind === 'confirmed' ? 'fcp-amount-green' : 'fcp-amount-blue'}>
                  {inrFull(m.amount_paise)}
                </td>
                <td>
                  <span className={`fcp-prob-badge ${
                    probability === 100 ? 'fcp-prob-100'
                    : probability >= 90  ? 'fcp-prob-90'
                    : 'fcp-prob-low'
                  }`}>
                    {probability}%
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      {hidden > 0 && (
        <div className="fcp-table-more">+{hidden} more settlements not shown</div>
      )}
    </>
  )
}
