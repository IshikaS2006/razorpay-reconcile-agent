import React, { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ArrowRight } from 'lucide-react'

function formatCompactInr(paise) {
  if (paise == null) return '—'
  const rupees = Number(paise) / 100
  if (Math.abs(rupees) >= 100000) {
    return `₹${(rupees / 100000).toFixed(1).replace(/\.0$/, '')}L`
  }
  return `₹${rupees.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

function formatDayLabel(period, index) {
  if (!period) return index === 0 ? 'Today' : `+${index}d`
  return String(period)
}

export default function CashForecastCard({ timeseriesData }) {
  const [hoverIndex, setHoverIndex] = useState(null)

  const forecastPoints = useMemo(() => {
    const forecast = timeseriesData?.forecast || []
    return forecast.map((item, index) => ({
      label: formatDayLabel(item.period, index),
      amount: Number(item.projected_cash_paise || 0),
      display: formatCompactInr(item.projected_cash_paise),
    }))
  }, [timeseriesData])

  const width = 380
  const height = 135
  const paddingLeft = 32
  const paddingRight = 15
  const chartHeight = 95
  const chartTop = 15

  if (forecastPoints.length === 0) {
    return (
      <article className="saas-card" aria-label="Cash Forecast Card">
        <div className="card-header">
          <h2 className="card-title">7 Day Cash Forecast</h2>
          <div className="forecast-header-right" title="Forecast duration">
            <span>Next 7 Days</span>
            <ChevronDown size={13} />
          </div>
        </div>

        <div className="chart-container" style={{ height: '175px', display: 'grid', placeItems: 'center', color: '#64748b' }}>
          No forecast data available for the latest run.
        </div>

        <Link to="/forecast" className="card-action-link" id="link-view-forecast">
          <span>View Forecast</span>
          <ArrowRight size={14} />
        </Link>
      </article>
    )
  }

  const maxVal = Math.max(...forecastPoints.map((p) => p.amount), 1)
  const minVal = Math.min(...forecastPoints.map((p) => p.amount), 0)
  const valueRange = Math.max(maxVal - minVal, 1)

  const points = forecastPoints.map((p, i) => {
    const x = forecastPoints.length === 1
      ? (width - paddingLeft - paddingRight) / 2 + paddingLeft
      : paddingLeft + (i / (forecastPoints.length - 1)) * (width - paddingLeft - paddingRight)
    const normY = (p.amount - minVal) / valueRange
    const y = chartTop + chartHeight - normY * chartHeight
    return { ...p, x, y }
  })

  const pathD = points.reduce((acc, pt, i, arr) => {
    if (i === 0) return `M ${pt.x} ${pt.y}`
    const prev = arr[i - 1]
    const cx1 = prev.x + (pt.x - prev.x) / 2
    const cy1 = prev.y
    const cx2 = prev.x + (pt.x - prev.x) / 2
    const cy2 = pt.y
    return `${acc} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${pt.x} ${pt.y}`
  }, '')

  const areaD = `${pathD} L ${points[points.length - 1].x} ${chartTop + chartHeight} L ${points[0].x} ${chartTop + chartHeight} Z`

  const gridValues = [maxVal, minVal + valueRange * 0.66, minVal + valueRange * 0.33, minVal]

  return (
    <article className="saas-card" aria-label="Cash Forecast Card">
      <div className="card-header">
        <h2 className="card-title">7 Day Cash Forecast</h2>
        <div className="forecast-header-right" title="Forecast duration">
          <span>Next 7 Days</span>
          <ChevronDown size={13} />
        </div>
      </div>

      <div className="chart-container" style={{ height: '175px' }}>
        <svg
          className="chart-svg"
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id="forecastGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0284c7" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#0284c7" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {gridValues.map((value, idx) => {
            const y = chartTop + (idx / (gridValues.length - 1)) * chartHeight
            return (
              <g key={idx}>
                <text
                  x="24"
                  y={y + 3.5}
                  fontSize="9"
                  fill="#94a3b8"
                  textAnchor="end"
                  fontFamily="inherit"
                >
                  {formatCompactInr(value)}
                </text>
                <line
                  x1="30"
                  y1={y}
                  x2={width - paddingRight}
                  y2={y}
                  stroke="#f1f5f9"
                  strokeWidth="1"
                />
              </g>
            )
          })}

          <path d={areaD} fill="url(#forecastGradient)" />
          <path
            d={pathD}
            fill="none"
            stroke="#2563eb"
            strokeWidth="2"
            strokeLinecap="round"
          />

          {points.map((pt, i) => (
            <g key={i}>
              <text
                x={pt.x}
                y={height - 2}
                fontSize="9.5"
                fill="#64748b"
                textAnchor="middle"
                fontFamily="inherit"
              >
                {pt.label}
              </text>
              <circle
                cx={pt.x}
                cy={pt.y}
                r={hoverIndex === i ? 4.5 : 3}
                fill="#2563eb"
                stroke="#ffffff"
                strokeWidth="1.5"
                style={{ cursor: 'pointer', transition: 'r 0.15s ease' }}
                onMouseEnter={() => setHoverIndex(i)}
                onMouseLeave={() => setHoverIndex(null)}
              />
            </g>
          ))}

          {hoverIndex !== null && points[hoverIndex] && (
            <g>
              <rect
                x={Math.max(10, Math.min(width - 76, points[hoverIndex].x - 33))}
                y={Math.max(2, points[hoverIndex].y - 24)}
                width="66"
                height="18"
                rx="4"
                fill="#0f172a"
              />
              <text
                x={Math.max(10, Math.min(width - 76, points[hoverIndex].x - 33)) + 33}
                y={Math.max(2, points[hoverIndex].y - 24) + 12}
                fill="#ffffff"
                fontSize="9.5"
                fontWeight="600"
                textAnchor="middle"
              >
                {points[hoverIndex].display}
              </text>
            </g>
          )}
        </svg>
      </div>

      <Link to="/forecast" className="card-action-link" id="link-view-forecast">
        <span>View Forecast</span>
        <ArrowRight size={14} />
      </Link>
    </article>
  )
}
