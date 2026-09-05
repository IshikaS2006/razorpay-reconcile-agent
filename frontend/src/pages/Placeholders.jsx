import React from 'react'
import { FileSpreadsheet, PlusCircle, Upload, FileCheck2 } from 'lucide-react'
import RoutePlaceholder from '../components/common/RoutePlaceholder'

export function NewReconciliationPage() {
  return (
    <RoutePlaceholder
      title="New Reconciliation"
      subtitle="The core reconciliation engine accepts Razorpay Settlement Reports and Bank Statements to automatically match transactions and detect cash discrepancies."
      icon={PlusCircle}
      badge="Next Up in Workflow"
    >
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
        gap: '16px',
        width: '100%',
        marginTop: '16px'
      }}>
        <div className="saas-card" style={{ padding: '16px', textAlign: 'left', border: '1px dashed #93c5fd' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <Upload size={18} color="#2563eb" />
            <strong style={{ fontSize: '13px' }}>1. Razorpay Settlement</strong>
          </div>
          <p style={{ fontSize: '12px', color: '#64748b' }}>Upload settlement CSV report with fees and taxes.</p>
        </div>

        <div className="saas-card" style={{ padding: '16px', textAlign: 'left', border: '1px dashed #93c5fd' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <Upload size={18} color="#2563eb" />
            <strong style={{ fontSize: '13px' }}>2. Bank Statement</strong>
          </div>
          <p style={{ fontSize: '12px', color: '#64748b' }}>Upload statement credits and reference IDs.</p>
        </div>

        <div className="saas-card" style={{ padding: '16px', textAlign: 'left', border: '1px dashed #cbd5e1' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <FileCheck2 size={18} color="#64748b" />
            <strong style={{ fontSize: '13px' }}>Validation</strong>
          </div>
          <p style={{ fontSize: '12px', color: '#64748b' }}>The app validates CSV structure before running settlement-to-bank reconciliation.</p>
        </div>
      </div>
    </RoutePlaceholder>
  )
}

export function ReconciliationsPage() {
  return (
    <RoutePlaceholder
      title="Reconciliations"
      subtitle="Historical log of reconciliation runs, matched settlements, unresolved cases, and exception review status."
      icon={FileSpreadsheet}
      badge="Reconciliations Queue"
    />
  )
}

export function RunDetailsPlaceholder() {
  return (
    <RoutePlaceholder
      title="Reconciliation Run Result"
      subtitle="This reconciliation run has been processed and stored for report and exception review."
      icon={FileSpreadsheet}
      badge="Run Complete"
    >
      <div style={{ display: 'flex', gap: '12px', marginTop: '14px', flexWrap: 'wrap', justifyContent: 'center' }}>
        <a href="/" className="btn-primary" style={{ display: 'inline-flex', padding: '8px 16px' }}>
          <span>View in Overview Dashboard</span>
        </a>
        <a href="/exceptions" className="btn-secondary-outline">
          <span>Review Exceptions</span>
        </a>
      </div>
    </RoutePlaceholder>
  )
}
