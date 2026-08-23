import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'
import './App.css'
import SummaryCard from './components/SummaryCard'
import MatchesTable from './components/MatchesTable'
import ExceptionCard from './components/ExceptionCard'

const API_URL = 'http://127.0.0.1:8000'

function isNotFound(error) {
  return error.response?.status === 404
}

function App() {
  const [run, setRun] = useState(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const fetchLatest = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const response = await axios.get(`${API_URL}/runs/latest`)
      setRun(response.data)
    } catch (requestError) {
      if (isNotFound(requestError)) setRun(null)
      else setError('We could not reach the reconciliation service. Check that the FastAPI backend is running and try again.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true
    axios.get(`${API_URL}/runs/latest`)
      .then((response) => { if (active) setRun(response.data) })
      .catch((requestError) => {
        if (!active) return
        if (isNotFound(requestError)) setRun(null)
        else setError('We could not reach the reconciliation service. Check that the FastAPI backend is running and try again.')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function runReconciliation() {
    setRunning(true)
    setError('')
    try {
      await axios.post(`${API_URL}/run`)
      await fetchLatest()
    } catch (requestError) {
      setError(isNotFound(requestError) ? 'The run completed, but no latest result is available yet.' : 'The reconciliation run could not be completed. Check the backend and try again.')
    } finally {
      setRunning(false)
    }
  }

  const exceptions = run?.exceptions ?? []
  const bankExceptions = exceptions.filter((item) => item.source === 'bank_reconciliation')
  const dbExceptions = exceptions.filter((item) => item.source === 'db_reconciliation')

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup"><div className="brand-mark">R</div><div><p className="eyebrow">Operations console</p><h1>Reconciliation</h1></div></div>
        <button className="run-button" type="button" onClick={runReconciliation} disabled={running}>{running && <span className="spinner" aria-hidden="true" />}{running ? 'Running reconciliation' : 'Run reconciliation'}</button>
      </header>
      <main>
        {error && <div className="error-banner" role="alert"><strong>Service unavailable.</strong> {error}</div>}
        {loading ? <div className="state-panel"><span className="large-spinner" aria-hidden="true" /><p>Loading latest reconciliation...</p></div> : run ? <>
          <div className="run-meta"><span>Latest run</span><time dateTime={run.summary?.run_at}>{run.summary?.run_at ? new Date(run.summary.run_at).toLocaleString() : 'Time unavailable'}</time>{run.summary?.run_id && <span className="run-id">Run {run.summary.run_id}</span>}</div>
          <SummaryCard summary={run.summary} />
          <MatchesTable matches={run.matches ?? []} />
          <section className="exceptions-section"><div className="section-heading"><div><p className="eyebrow">Review queue</p><h2>Exceptions</h2></div><span className="section-count">{exceptions.length} total</span></div><ExceptionGroup title="Bank Reconciliation" items={bankExceptions} /><ExceptionGroup title="Internal Order DB Reconciliation" items={dbExceptions} /></section>
        </> : <div className="state-panel empty-state"><div className="empty-icon">+</div><h2>No reconciliation runs yet</h2><p>Run your first reconciliation to see settlement matches and exceptions here.</p><button className="secondary-button" type="button" onClick={runReconciliation}>Run reconciliation</button></div>}
      </main>
    </div>
  )
}

function ExceptionGroup({ title, items }) {
  const [open, setOpen] = useState(true)
  return <div className="exception-group"><button className="group-toggle" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open}><span className={`chevron ${open ? 'is-open' : ''}`} aria-hidden="true">›</span><span>{title}</span><span className="group-count">{items.length}</span></button>{open && <div className="exception-list">{items.length ? items.map((item, index) => <ExceptionCard key={`${item.reference_id}-${index}`} exception={item} />) : <p className="no-items">No exceptions in this group.</p>}</div>}</div>
}

export default App
