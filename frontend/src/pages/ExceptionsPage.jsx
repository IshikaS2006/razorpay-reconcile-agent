import React, { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'

// Redirect old /exceptions routes to the new reconciliation workflow
export default function ExceptionsPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const runId = searchParams.get('run')

  useEffect(() => {
    if (runId) {
      navigate(`/reconciliations/${runId}#report`, { replace: true })
    } else {
      navigate('/reconciliations', { replace: true })
    }
  }, [navigate, runId])

  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      alignItems: 'center', 
      justifyContent: 'center', 
      minHeight: '60vh',
      gap: '16px',
      textAlign: 'center',
      padding: '40px'
    }}>
      <AlertCircle size={48} color="#2563eb" />
      <h2 style={{ fontSize: '18px', fontWeight: 600, color: '#0f172a' }}>
        Navigation Updated
      </h2>
      <p style={{ fontSize: '14px', color: '#64748b', maxWidth: '400px' }}>
        Exceptions are now part of the Reconciliation workflow. Redirecting you to the new location...
      </p>
    </div>
  )
}
