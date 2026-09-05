import React, { useEffect, useState, useCallback } from 'react'
import axios from 'axios'
import TopHeader from '../components/layout/TopHeader'
import SummaryKpiGrid from '../components/overview/SummaryKpiGrid'
import CashPositionCard from '../components/overview/CashPositionCard'
import CashForecastCard from '../components/overview/CashForecastCard'
import AccuracyCard from '../components/overview/AccuracyCard'
import RecentExceptionsCard from '../components/overview/RecentExceptionsCard'
import ReconciliationOverviewCard from '../components/overview/ReconciliationOverviewCard'

const API_URL = 'http://127.0.0.1:8000'

export default function OverviewPage() {
  const [run, setRun] = useState(null)
  const [accuracyReport, setAccuracyReport] = useState(null)
  const [cashPositionData, setCashPositionData] = useState(null)
  const [timeseriesData, setTimeseriesData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchOverviewData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      // 1. Fetch latest run
      const runRes = await axios.get(`${API_URL}/runs/latest`, { timeout: 4000 })
      const runData = runRes.data
      setRun(runData)

      const runId = runData?.summary?.run_id
      if (runId) {
        // Fetch remaining data in parallel
        const [accRes, cashRes, timeRes] = await Promise.allSettled([
          axios.get(`${API_URL}/accuracy-report/${runId}`, { timeout: 4000 }),
          axios.get(`${API_URL}/forecast/${runId}`, { timeout: 4000 }),
          axios.get(`${API_URL}/cash-forecast/timeseries/${runId}`, { timeout: 4000 })
        ])

        if (accRes.status === 'fulfilled') setAccuracyReport(accRes.value.data)
        if (cashRes.status === 'fulfilled') setCashPositionData(cashRes.value.data)
        if (timeRes.status === 'fulfilled') setTimeseriesData(timeRes.value.data)

      }
    } catch (err) {
      // If 404, there are simply no runs yet
      if (err.response?.status === 404) {
        setRun(null)
      } else {
        setError('Backend reconciliation service is offline. Live metrics are unavailable until it reconnects.')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchOverviewData()
  }, [fetchOverviewData])

  return (
    <div className="overview-page">
      <TopHeader
        title="Overview"
        subtitle="Reconcile settlements. Detect issues. Own your cash position."
        dateRange="20 May 2026 – 26 May 2026"
      />

      {error && (
        <div className="status-banner error" role="alert">
          <span>{error}</span>
          <button
            type="button"
            onClick={fetchOverviewData}
            style={{ fontWeight: 600, textDecoration: 'underline', color: 'inherit' }}
          >
            Retry connection
          </button>
        </div>
      )}

      {/* 5 Top Summary KPI Cards */}
      <SummaryKpiGrid
        summary={run?.summary}
        resolutionSummary={run?.resolution_summary}
        accuracyReport={accuracyReport}
      />

      {/* Middle Row: Cash Position, 7 Day Forecast, Accuracy */}
      <section className="middle-grid" aria-label="Financial and Accuracy Insights">
        <CashPositionCard cashPositionData={cashPositionData} timeseriesData={timeseriesData} />
        <CashForecastCard timeseriesData={timeseriesData} />
        <AccuracyCard
          runId={run?.summary?.run_id}
          summary={run?.summary}
          accuracyReport={accuracyReport}
        />
      </section>

      {/* Bottom Row: Recent Exceptions and Reconciliation Overview */}
      <section className="bottom-grid" aria-label="Exceptions and Breakdown">
        <RecentExceptionsCard
          liveExceptions={run?.exceptions}
          runId={run?.summary?.run_id}
        />
        <ReconciliationOverviewCard
          summary={run?.summary}
          resolutionSummary={run?.resolution_summary}
        />
      </section>
    </div>
  )
}
