import { useEffect, useState } from 'react'
import axios from 'axios'

const API_URL = 'http://127.0.0.1:8000'

function formatAmount(paise) {
  return `₹${(Number(paise ?? 0) / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function ForecastCard({ runId }) {
  const [forecast, setForecast] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!runId) return
    let active = true
    setForecast(null)
    setError('')
    axios.get(`${API_URL}/forecast/${runId}`)
      .then((response) => { if (active) setForecast(response.data) })
      .catch(() => { if (active) setError('Cash position is unavailable for this run.') })
    return () => { active = false }
  }, [runId])

  if (error) return <section className="forecast-card" aria-label="Cash position"><div className="section-heading"><div><p className="eyebrow">Cash position</p><h2>Snapshot unavailable</h2></div></div><p className="forecast-error">{error}</p></section>
  if (!forecast) return <section className="forecast-card" aria-label="Cash position"><div className="section-heading"><div><p className="eyebrow">Cash position</p><h2>Loading snapshot...</h2></div></div></section>

  const confirmed = Number(forecast.confirmed_total ?? 0)
  const atRisk = Number(forecast.at_risk_total ?? 0)
  const total = confirmed + atRisk
  const confirmedWidth = total ? `${(confirmed / total) * 100}%` : '100%'

  return <section className="forecast-card" aria-label="Cash position">
    <div className="section-heading"><div><p className="eyebrow">Cash position</p><h2>Confirmed vs at risk</h2></div><span className="section-count">Snapshot</span></div>
    <div className="forecast-total"><strong>{formatAmount(total)}</strong><span>tracked cash</span></div>
    <div className="forecast-bar" role="img" aria-label={`${formatAmount(confirmed)} confirmed and ${formatAmount(atRisk)} at risk`}><div className="forecast-bar-confirmed" style={{ width: confirmedWidth }} /><div className="forecast-bar-risk" /></div>
    <div className="forecast-legend"><span><i className="forecast-swatch confirmed" />Confirmed <strong>{formatAmount(confirmed)}</strong></span><span><i className="forecast-swatch risk" />At risk <strong>{formatAmount(atRisk)}</strong></span></div>
    <div className="forecast-actions"><p className="eyebrow">Ranked next steps</p>{forecast.recommended_next_steps?.length ? <ol>{forecast.recommended_next_steps.map((step) => <li key={`${step.source_id}-${step.reference_id}`}><div><strong>{step.action || 'Review this item using the cited record.'}</strong><span>{step.bucket.replaceAll('_', ' ')} · {step.reference_id} · {formatAmount(step.amount_paise)} · {step.source_id}</span></div></li>)}</ol> : <p className="forecast-empty">No bucketed at-risk items in this run.</p>}</div>
  </section>
}

export default ForecastCard
