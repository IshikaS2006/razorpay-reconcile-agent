import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import TopNav from './components/layout/TopNav'
import NewReconciliationPage from './pages/NewReconciliationPage'
import RunDetailsPage from './pages/RunDetailsPage'
import ReconciliationsListPage from './pages/ReconciliationsListPage'
import ExceptionDetailPage from './pages/ExceptionDetailPage'
import ForecastPage from './pages/ForecastPage'
import ExceptionsPage from './pages/ExceptionsPage'
import InvestigationsPage from './pages/InvestigationsPage'
import MetricsPage from './pages/MetricsPage'

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <TopNav />

        <main className="app-main">
          <div className="app-content">
            <Routes>
              {/* Root → Reconciliations list */}
              <Route path="/" element={<Navigate to="/reconciliations" replace />} />
              <Route path="/overview" element={<Navigate to="/reconciliations" replace />} />

              {/* New reconciliation — accessible via direct URL only */}
              <Route path="/reconciliation/new"  element={<NewReconciliationPage />} />
              <Route path="/reconciliations/new" element={<NewReconciliationPage />} />

              {/* Reconciliation workflow */}
              <Route path="/reconciliations/:runId/exceptions/:refId" element={<RunDetailsPage />} />
              <Route path="/reconciliations/:runId" element={<RunDetailsPage />} />
              <Route path="/reconciliations" element={<ReconciliationsListPage />} />

              {/* Core pages */}
              <Route path="/forecast" element={<ForecastPage />} />
              <Route path="/metrics"  element={<MetricsPage />} />

              {/* Legacy redirects */}
              <Route path="/exceptions"        element={<ExceptionsPage />} />
              <Route path="/exceptions/detail" element={<ExceptionsPage />} />
              <Route path="/investigations"    element={<InvestigationsPage />} />

              {/* Removed pages */}
              <Route path="/cash-position" element={<Navigate to="/reconciliations" replace />} />
              <Route path="/data-sources"  element={<Navigate to="/reconciliations" replace />} />
              <Route path="/ask"           element={<Navigate to="/reconciliations" replace />} />
              <Route path="/settings"      element={<Navigate to="/reconciliations" replace />} />

              {/* Fallback */}
              <Route path="*" element={<Navigate to="/reconciliations" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </BrowserRouter>
  )
}
