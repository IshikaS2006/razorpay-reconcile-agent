import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import axios from 'axios'
import {
  Wallet, TrendingUp, Calendar, Download,
  AlertTriangle, CheckCircle2, Clock, ArrowUp, ArrowDown,
  FileText, ChevronRight, BarChart3, PieChart, Info
} from 'lucide-react'
import { fmtAmount, exLabel } from '../utils/exceptions'

const API = 'http://127.0.0.1:8000'

function fmtDt(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true
  })
}

function SevBadge({ level }) {
  const cls = { High: 'ep-sev-high', Medium: 'ep-sev-medium', Low: 'ep-sev-low' }[level] || 'ep-sev-low'
  const Icon = level === 'High' ? AlertTriangle : level === 'Medium' ? AlertTriangle : Clock
  return <span className={`ep-sev-badge ${cls}`}><Icon size={11} /> {level}</span>
}

function formatDateRange(rows) {
  const validDates = rows
    .map((row) => row.date || row.posted_at || row.created_at || null)
    .filter(Boolean)
    .map((value) => new Date(value))
    .filter((date) => !Number.isNaN(date.getTime()))
    .sort((a, b) => a - b)

  if (validDates.length === 0) return 'Latest run'

  const start = validDates[0].toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  const end = validDates[validDates.length - 1].toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  return start === end ? start : `${start} – ${end}`
}

function buildMovement(row, fallbackType) {
  const amountPaise = Number(row.amount_paise || row.projected_amount_paise || 0)
  return {
    id: row.id || row.reference_id || row.source_id || `${fallbackType}-${row.date || row.period || Math.random()}`,
    date: row.date || row.posted_at || row.created_at || null,
    type: fallbackType,
    description: row.description || row.reference_id || row.period || 'Settlement-linked movement',
    source: row.source || row.source_id || 'Reconciliation run',
    amount: amountPaise,
    status: row.status || (fallbackType === 'projected' ? 'Projected' : 'Tracked'),
  }
}

function TrendChart({ points }) {
  if (!points.length) {
    return <div className="cp-empty-state"><Info size={18} color="#64748b" /><span>No trend data available for this run</span></div>
  }

  const width = 800
  const height = 300
  const padX = 24
  const padY = 30
  const values = points.flatMap((p) => [p.confirmed, p.atRisk, p.net])
  const minVal = Math.min(...values, 0)
  const maxVal = Math.max(...values, 1)
  const range = Math.max(maxVal - minVal, 1)

  const mapPoint = (value, index, total) => {
    const x = total === 1 ? width / 2 : padX + (index / (total - 1)) * (width - padX * 2)
    const y = padY + (1 - (value - minVal) / range) * (height - padY * 2)
    return `${x},${y}`
  }

  const confirmedLine = points.map((p, i) => mapPoint(p.confirmed, i, points.length)).join(' ')
  const atRiskLine = points.map((p, i) => mapPoint(p.atRisk, i, points.length)).join(' ')
  const netLine = points.map((p, i) => mapPoint(p.net, i, points.length)).join(' ')

  return (
    <>
      <svg className="cp-chart-svg" viewBox={`0 0 ${width} ${height}`}>
        {[0, 1, 2, 3, 4].map(i => {
          const y = i * 60 + 30
          return <line key={i} x1="0" y1={y} x2={width} y2={y} stroke="#e2e8f0" strokeWidth="1" />
        })}
        <polyline fill="none" stroke="#1e56a0" strokeWidth="2" points={confirmedLine} />
        <polyline fill="none" stroke="#f59e0b" strokeWidth="2" strokeDasharray="5,5" points={atRiskLine} />
        <polyline fill="none" stroke="#10b981" strokeWidth="3" points={netLine} />
      </svg>
      <div className="cp-chart-legend">
        <div className="cp-legend-item"><div className="cp-legend-dot cp-legend-blue" /><span>Confirmed Cash</span></div>
        <div className="cp-legend-item"><div className="cp-legend-dot cp-legend-amber" /><span>At-risk Cash</span></div>
        <div className="cp-legend-item"><div className="cp-legend-dot cp-legend-green" /><span>Net Cash Position</span></div>
      </div>
    </>
  )
}

export default function CashPositionPage() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState([])
  const [selectedRunId, setSelectedRunId] = useState(null)
  const [cashData, setCashData] = useState(null)
  const [forecastData, setForecastData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [timeRange, setTimeRange] = useState('7D')
  const [movementTab, setMovementTab] = useState('all')

  useEffect(() => {
    axios.get(`${API}/runs`).then(r => {
      const rs = r.data || []
      setRuns(rs)
      if (rs.length > 0) setSelectedRunId(rs[0].run_id)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedRunId) return
    setLoading(true)
    Promise.all([
      axios.get(`${API}/forecast/${selectedRunId}`),
      axios.get(`${API}/cash-forecast/timeseries/${selectedRunId}`)
    ]).then(([cashRes, forecastRes]) => {
      setCashData(cashRes.data)
      setForecastData(forecastRes.data)
    }).catch(() => {
      setCashData(null)
      setForecastData(null)
    }).finally(() => setLoading(false))
  }, [selectedRunId])

  const confirmedCash = Number(cashData?.confirmed_total || 0)
  const atRiskCash = Number(cashData?.at_risk_total || 0)
  const netCashPosition = confirmedCash - atRiskCash
  const exceptions = cashData?.recommended_next_steps || []
  const atRiskExceptions = exceptions.slice(0, 5)

  const confirmedInflows = forecastData?.inflow_rows?.confirmed || []
  const projectedInflows = forecastData?.inflow_rows?.projected || []
  const outflowRows = forecastData?.outflow_rows || []
  const forecastRows = forecastData?.forecast || []

  const expectedInflows = [...confirmedInflows, ...projectedInflows]
    .reduce((sum, row) => sum + Number(row.amount_paise || 0), 0)
  const expectedOutflows = outflowRows
    .reduce((sum, row) => sum + Number(row.amount_paise || 0), 0)

  const allMovementRows = useMemo(() => {
    const inflowItems = [
      ...confirmedInflows.map((row) => buildMovement(row, 'inflow')),
      ...projectedInflows.map((row) => buildMovement(row, 'inflow')),
    ]
    const outflowItems = outflowRows.map((row) => buildMovement(row, 'outflow'))

    return [...inflowItems, ...outflowItems]
      .sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0))
  }, [confirmedInflows, projectedInflows, outflowRows])

  const filteredMovements = movementTab === 'all'
    ? allMovementRows
    : allMovementRows.filter(m => m.type === movementTab)

  const chartPoints = useMemo(() => {
    return forecastRows.map((row, index) => {
      const confirmed = Number(row.confirmed_cash_paise ?? row.projected_cash_paise ?? 0)
      const atRisk = Number(row.at_risk_cash_paise ?? atRiskCash)
      const net = Number(row.projected_cash_paise ?? (confirmed - atRisk))
      return {
        label: row.period || `P${index + 1}`,
        confirmed,
        atRisk,
        net,
      }
    })
  }, [forecastRows, atRiskCash])

  const chartDateRange = formatDateRange(allMovementRows)
  const breakdownTotal = confirmedCash + atRiskCash + expectedInflows + expectedOutflows
  const projectedNetCash = forecastRows.length > 0
    ? Number(forecastRows[forecastRows.length - 1].projected_cash_paise || 0)
    : null

  const handleExceptionClick = (exception) => {
    const refId = exception.reference_id || exception.id
    navigate(`/reconciliations/${selectedRunId}?exception=${encodeURIComponent(refId)}`)
  }

  const handleExportReport = () => {
    console.log('Exporting cash position report for run', selectedRunId)
  }

  return (
    <div className="cp-page">
      <div className="cp-header-row">
        <div className="cp-header-left">
          <h1 className="cp-page-title">Cash Position</h1>
          <p className="cp-page-subtitle">Live view of settlement-linked cash from the latest reconciliation run.</p>
        </div>
        <div className="cp-header-actions">
          <button className="btn-secondary-outline cp-export-btn" onClick={handleExportReport}>
            <Download size={14} /> Export Report
          </button>
        </div>
      </div>

      <div className="cp-date-row">
        <div className="cp-date-selector">
          <Calendar size={14} className="cp-date-icon" />
          <span className="cp-date-text">{chartDateRange}</span>
        </div>
      </div>

      <div className="cp-kpi-grid">
        <div className="cp-kpi-card">
          <div className="cp-kpi-header"><div className="cp-kpi-icon cp-kpi-blue"><Wallet size={18} /></div><span className="cp-kpi-label">Confirmed Cash</span></div>
          <div className="cp-kpi-value">{fmtAmount(confirmedCash)}</div>
          <div className="cp-kpi-trend">Live from matched settlement credits</div>
        </div>

        <div className="cp-kpi-card">
          <div className="cp-kpi-header"><div className="cp-kpi-icon cp-kpi-amber"><AlertTriangle size={18} /></div><span className="cp-kpi-label">At-risk Cash</span></div>
          <div className="cp-kpi-value">{fmtAmount(atRiskCash)}</div>
          <div className="cp-kpi-trend">Amounts still blocked by open exceptions</div>
        </div>

        <div className="cp-kpi-card">
          <div className="cp-kpi-header"><div className="cp-kpi-icon cp-kpi-green"><ArrowDown size={18} /></div><span className="cp-kpi-label">Expected Inflows</span></div>
          <div className="cp-kpi-value">{fmtAmount(expectedInflows)}</div>
          <div className="cp-kpi-trend">From confirmed and projected inflow rows</div>
        </div>

        <div className="cp-kpi-card">
          <div className="cp-kpi-header"><div className="cp-kpi-icon cp-kpi-red"><ArrowUp size={18} /></div><span className="cp-kpi-label">Expected Outflows</span></div>
          <div className="cp-kpi-value">{fmtAmount(expectedOutflows)}</div>
          <div className="cp-kpi-trend">From forecast outflow rows only</div>
        </div>

        <div className="cp-kpi-card cp-kpi-highlight">
          <div className="cp-kpi-header"><div className="cp-kpi-icon cp-kpi-purple"><TrendingUp size={18} /></div><span className="cp-kpi-label">Net Cash Position</span></div>
          <div className="cp-kpi-value">{fmtAmount(netCashPosition)}</div>
          <div className="cp-kpi-trend">Confirmed cash minus at-risk cash</div>
        </div>
      </div>

      <div className="cp-main-grid">
        <div className="cp-main-col">
          <div className="cp-card cp-chart-card">
            <div className="cp-card-header">
              <div className="cp-card-title"><BarChart3 size={16} /> Cash Balance Trend</div>
              <div className="cp-time-controls">
                {['7D', '30D', '90D', 'Custom'].map(range => (
                  <button
                    key={range}
                    className={`cp-time-btn ${timeRange === range ? 'cp-time-active' : ''}`}
                    onClick={() => setTimeRange(range)}
                  >
                    {range}
                  </button>
                ))}
              </div>
            </div>
            <div className="cp-chart-container">
              <TrendChart points={chartPoints} />
            </div>
          </div>

          <div className="cp-card">
            <div className="cp-card-header">
              <div className="cp-card-title"><FileText size={16} /> Recent Cash Movements</div>
              <div className="cp-tab-controls">
                {['All', 'Inflows', 'Outflows'].map(tab => (
                  <button
                    key={tab.toLowerCase()}
                    className={`cp-tab-btn ${movementTab === tab.toLowerCase() ? 'cp-tab-active' : ''}`}
                    onClick={() => setMovementTab(tab.toLowerCase())}
                  >
                    {tab}
                  </button>
                ))}
              </div>
            </div>

            <div className="cp-movements-table">
              {filteredMovements.length > 0 ? (
                <table className="cp-table">
                  <thead>
                    <tr>
                      <th>Date & Time</th>
                      <th>Type</th>
                      <th>Description</th>
                      <th>Source</th>
                      <th>Amount</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMovements.map((movement) => (
                      <tr key={movement.id}>
                        <td className="cp-date-cell">{fmtDt(movement.date)}</td>
                        <td>
                          <span className={`cp-type-badge cp-type-${movement.type}`}>
                            {movement.type === 'inflow' ? <ArrowDown size={12} /> : <ArrowUp size={12} />}
                            {movement.type.charAt(0).toUpperCase() + movement.type.slice(1)}
                          </span>
                        </td>
                        <td className="cp-description-cell">{movement.description}</td>
                        <td className="cp-source-cell">{movement.source}</td>
                        <td className={`cp-amount-cell cp-amount-${movement.type}`}>
                          {movement.type === 'inflow' ? '+' : '-'}{fmtAmount(movement.amount)}
                        </td>
                        <td>
                          <span className="cp-status-badge cp-status-matched">
                            <CheckCircle2 size={10} /> {movement.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="cp-empty-state">
                  <Info size={20} color="#64748b" />
                  <span>No movement rows were returned for this run.</span>
                </div>
              )}
            </div>

            <div className="cp-card-footer">
              <span className="cp-view-link">{allMovementRows.length} tracked movement{allMovementRows.length !== 1 ? 's' : ''}</span>
            </div>
          </div>

          <div className="cp-card cp-about-card">
            <div className="cp-about-title"><Info size={14} /> About Cash Position</div>
            <div className="cp-about-text">
              This page uses only live reconciliation outputs: confirmed settlement-linked cash, at-risk exceptions, and forecast timeseries rows returned by the backend.
            </div>
          </div>
        </div>

        <div className="cp-side-col">
          <div className="cp-card">
            <div className="cp-card-title"><PieChart size={16} /> Cash Breakdown</div>

            {breakdownTotal > 0 ? (
              <>
                <div className="cp-breakdown-chart">
                  <svg className="cp-donut-chart" viewBox="0 0 200 200">
                    <circle cx="100" cy="100" r="80" fill="none" stroke="#e2e8f0" strokeWidth="20" />
                    <circle cx="100" cy="100" r="80" fill="none" stroke="#1e56a0" strokeWidth="20"
                      strokeDasharray={`${(confirmedCash / breakdownTotal) * 502} 502`}
                      transform="rotate(-90 100 100)" />
                    <circle cx="100" cy="100" r="80" fill="none" stroke="#f59e0b" strokeWidth="20"
                      strokeDasharray={`${(atRiskCash / breakdownTotal) * 502} 502`}
                      strokeDashoffset={`-${(confirmedCash / breakdownTotal) * 502}`}
                      transform="rotate(-90 100 100)" />
                    <circle cx="100" cy="100" r="80" fill="none" stroke="#10b981" strokeWidth="20"
                      strokeDasharray={`${(expectedInflows / breakdownTotal) * 502} 502`}
                      strokeDashoffset={`-${((confirmedCash + atRiskCash) / breakdownTotal) * 502}`}
                      transform="rotate(-90 100 100)" />
                  </svg>

                  <div className="cp-donut-center">
                    <div className="cp-donut-value">{fmtAmount(netCashPosition)}</div>
                    <div className="cp-donut-label">Net Position</div>
                  </div>
                </div>

                <div className="cp-breakdown-legend">
                  <div className="cp-breakdown-item"><div className="cp-breakdown-dot cp-breakdown-blue" /><span>Confirmed Cash</span><span className="cp-breakdown-value">{fmtAmount(confirmedCash)}</span></div>
                  <div className="cp-breakdown-item"><div className="cp-breakdown-dot cp-breakdown-amber" /><span>At-risk Cash</span><span className="cp-breakdown-value">{fmtAmount(atRiskCash)}</span></div>
                  <div className="cp-breakdown-item"><div className="cp-breakdown-dot cp-breakdown-green" /><span>Pending Inflows</span><span className="cp-breakdown-value">{fmtAmount(expectedInflows)}</span></div>
                  <div className="cp-breakdown-item"><div className="cp-breakdown-dot cp-breakdown-red" /><span>Pending Outflows</span><span className="cp-breakdown-value">{fmtAmount(expectedOutflows)}</span></div>
                </div>
              </>
            ) : (
              <div className="cp-empty-state">
                <Info size={20} color="#64748b" />
                <span>No cash breakdown is available for this run.</span>
              </div>
            )}
          </div>

          <div className="cp-card">
            <div className="cp-card-title"><AlertTriangle size={16} /> At-risk Exception Flags</div>
            <p className="cp-card-subtitle" style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
              Exception flags that could impact cash position
            </p>

            <div className="cp-exceptions-list">
              {atRiskExceptions.length > 0 ? atRiskExceptions.map((exception, i) => (
                <div
                  key={i}
                  className="cp-exception-item"
                  onClick={() => handleExceptionClick(exception)}
                >
                  <div className="cp-exception-left">
                    <div className="cp-exception-icon"><AlertTriangle size={14} /></div>
                    <div className="cp-exception-info">
                      <div className="cp-exception-name">{exLabel(exception.bucket)}</div>
                      <div className="cp-exception-ref">{exception.reference_id || '—'}</div>
                    </div>
                  </div>
                  <div className="cp-exception-right">
                    <div className="cp-exception-amount">{fmtAmount(exception.amount_paise)}</div>
                    <SevBadge level={exception.amount_paise > 100000 ? 'High' : exception.amount_paise > 50000 ? 'Medium' : 'Low'} />
                  </div>
                </div>
              )) : (
                <div className="cp-empty-state"><CheckCircle2 size={20} color="#10b981" /><span>No at-risk exception flags found</span></div>
              )}
            </div>

            {atRiskExceptions.length > 0 && (
              <div className="cp-total-risk">
                <span>Total At-risk Cash</span>
                <span className="cp-total-risk-value">{fmtAmount(atRiskCash)}</span>
              </div>
            )}

            <div className="cp-card-footer">
              <Link to={`/reconciliations/${selectedRunId}#report`} className="cp-view-link">
                View all exceptions <ChevronRight size={12} />
              </Link>
            </div>
          </div>

          <div className="cp-card">
            <div className="cp-card-title"><TrendingUp size={16} /> 7-Day Cash Projection</div>

            {forecastRows.length > 0 ? (
              <>
                <div className="cp-projection-chart">
                  <svg className="cp-mini-chart" viewBox="0 0 300 150">
                    <polyline
                      fill="none"
                      stroke="#1e56a0"
                      strokeWidth="2"
                      points={forecastRows.map((row, index) => {
                        const x = forecastRows.length === 1 ? 150 : (index / (forecastRows.length - 1)) * 300
                        const values = forecastRows.map(item => Number(item.projected_cash_paise || 0))
                        const min = Math.min(...values, 0)
                        const max = Math.max(...values, 1)
                        const range = Math.max(max - min, 1)
                        const y = 120 - ((Number(row.projected_cash_paise || 0) - min) / range) * 90
                        return `${x},${y}`
                      }).join(' ')}
                    />
                    {(() => {
                      const lastIndex = forecastRows.length - 1
                      const values = forecastRows.map(item => Number(item.projected_cash_paise || 0))
                      const min = Math.min(...values, 0)
                      const max = Math.max(...values, 1)
                      const range = Math.max(max - min, 1)
                      const x = forecastRows.length === 1 ? 150 : (lastIndex / (forecastRows.length - 1)) * 300
                      const y = 120 - ((Number(forecastRows[lastIndex].projected_cash_paise || 0) - min) / range) * 90
                      return <circle cx={x} cy={y} r="4" fill="#1e56a0" />
                    })()}
                  </svg>
                  <div className="cp-projection-info">
                    <div className="cp-projection-label">Projected Net Cash</div>
                    <div className="cp-projection-value">{projectedNetCash == null ? '—' : fmtAmount(projectedNetCash)}</div>
                    <div className="cp-projection-sub">From the latest backend forecast point</div>
                  </div>
                </div>
              </>
            ) : (
              <div className="cp-empty-state">
                <Info size={20} color="#64748b" />
                <span>No forecast projection is available for this run.</span>
              </div>
            )}

            <div className="cp-card-footer">
              <Link to="/forecast" className="cp-view-link">
                View full forecast <ChevronRight size={12} />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
