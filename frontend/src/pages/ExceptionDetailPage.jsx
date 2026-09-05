import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate, useParams, useSearchParams, Link } from 'react-router-dom'
import axios from 'axios'
import {
  ChevronLeft, ChevronRight, AlertTriangle, CheckCircle2, Clock, ArrowRight,
  FileText, Cpu, AlertCircle, Info, ShieldCheck,
  ThumbsUp, ThumbsDown, Flag, Eye, Loader2, Upload, Paperclip,
  Calendar, MapPin, User, Search, FileCheck, XCircle
} from 'lucide-react'
import {
  exLabel, fmtAmount, severityOf, statusLabel, statusChipClass,
  isNeedsReview, isAutoResolved, sourceLabel, impactText, ageOf
} from '../utils/exceptions'

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

function StatusChip({ status }) {
  return <span className={`ep-status-chip ${statusChipClass(status)}`}>{statusLabel(status)}</span>
}

export default function ExceptionDetailPage() {
  const { runId } = useParams()
  const { refId } = useParams()
  const [searchParams] = useSearchParams()

  const [runData, setRunData] = useState(null)
  const [exception, setException] = useState(null)
  const [loading, setLoading] = useState(true)
  const [resolving, setResolving] = useState(false)
  const [resolveError, setResolveError] = useState(null)
  const [localStatus, setLocalStatus] = useState(null)
  const [notes, setNotes] = useState('')
  const [assignedTo, setAssignedTo] = useState('Unassigned')
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [auditLog, setAuditLog] = useState([])
  const [attachment, setAttachment] = useState(null)

  const loadException = useCallback(async () => {
    if (!runId || !refId) return
    setLoading(true)
    try {
      const r = await axios.get(`${API}/runs/${runId}`)
      setRunData(r.data)
      const exc = r.data?.exceptions?.find(e => e.reference_id === refId)
      if (exc) {
        setException(exc)
        setLocalStatus(exc.status)
      }
    } catch {
      setRunData(null)
      setException(null)
    } finally {
      setLoading(false)
    }
  }, [runId, refId])

  useEffect(() => { loadException() }, [loadException])

  const sev = severityOf(exception)
  const match = runData?.matches?.find(m => m.settlement_id === refId)
  const currentStatus = localStatus || exception?.status
  const isMissingCredit = exception?.exception_type === 'unresolved_settlement'
  const expectedAmountPaise = match?.expected_amount_paise ?? match?.settled_amount ?? exception?.amount_paise ?? null
  const detectedAmountPaise = match?.actual_amount_paise ?? match?.settled_amount ?? null
  const differencePaise = match?.amount_gap_paise ?? (expectedAmountPaise != null && detectedAmountPaise != null ? Math.abs(expectedAmountPaise - detectedAmountPaise) : expectedAmountPaise)
  const matchLabel = match ? `${match.tier || 'match'}${match.match_subtype ? ` · ${match.match_subtype}` : ''}` : 'No match'
  const auditEntries = [
    {
      action: 'Detected',
      by: exception?.source || 'system',
      at: runData?.summary?.run_at,
      detail: `${exLabel(exception?.exception_type)} recorded for ${refId}`,
    },
    ...(exception?.investigation ? [{
      action: statusLabel(exception.investigation.status),
      by: 'Investigation Engine',
      at: exception.investigation.investigated_at,
      detail: exception.investigation.explanation,
    }] : []),
    ...auditLog,
  ].filter(Boolean)

  const resolve = async (action) => {
    if (!runId || !refId) return
    setResolving(true)
    setResolveError(null)
    try {
      const r = await axios.post(`${API}/resolve/${runId}`, {
        reference_id: refId,
        action,
        reason: `Manual ${action} from exception detail page`,
        actor: 'Finance Manager',
      })
      setLocalStatus(r.data.new_status)
      setAuditLog(log => [{
        action,
        by: r.data.actor,
        at: r.data.resolved_at,
        prevStatus: r.data.prev_status,
        newStatus: r.data.new_status,
        reason: r.data.reason,
      }, ...log])
      await loadException()
    } catch {
      setResolveError('Resolution failed. Please try again.')
    } finally {
      setResolving(false)
    }
  }

  const handleFileUpload = (e) => {
    const file = e.target.files[0]
    if (file) {
      setAttachment(file)
    }
  }

  const handleAssign = () => {
    setShowAssignModal(true)
  }

  const handleSaveNotes = () => {
    // In a real implementation, this would save to the backend
    console.log('Saving notes:', notes)
    setNotes('')
  }

  if (!runId || !refId) {
    return (
      <div className="exd-page">
        <div className="inv-empty-state">
          <AlertCircle size={32} color="#e11d48" />
          <p>No exception selected. Go to <Link to="/reconciliations" className="ep-link-btn">Reconciliations</Link> and open a run.</p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="exd-page">
        <div className="inv-empty-state"><div className="rd-spinner" /> Loading exception details…</div>
      </div>
    )
  }

  if (!exception) {
    return (
      <div className="exd-page">
        <div className="inv-empty-state">
          <AlertCircle size={24} color="#d97706" />
          <p>Exception <code>{refId}</code> not found in Run #{runId}.</p>
          <Link to={`/reconciliations/${runId}`} className="ep-link-btn">← Back to Reconciliation Run</Link>
        </div>
      </div>
    )
  }

  const showActions = isNeedsReview(currentStatus) && !resolving

  return (
    <div className="exd-page">
      {/* Header */}
      <div className="exd-header-row">
        <div className="exd-header-left">
          <Link to={`/reconciliations/${runId}`} className="exd-back-link">
            <ChevronLeft size={14} /> Back to Reconciliation Run
          </Link>
          <div className="exd-title-row">
            <h1 className="exd-page-title">{exLabel(exception.exception_type)}</h1>
            <SevBadge level={sev} />
            <StatusChip status={currentStatus} />
          </div>
          <p className="exd-page-subtitle">Investigate the issue and take appropriate action.</p>
        </div>
        <div className="exd-header-right">
          <div className="exd-nav-actions">
            <Link to={`/reconciliations/${runId}`} className="exd-nav-link">
              View in Run #{runId} <ChevronRight size={12} />
            </Link>
            <button className="exd-nav-btn" title="Previous exception">
              <ChevronLeft size={14} />
            </button>
            <button className="exd-nav-btn" title="Next exception">
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      </div>

      <div className="exd-body">
        <div className="exd-main-col">
          {/* Section 1: Exception Summary */}
          <div className="exd-card">
            <div className="exd-card-title"><FileText size={14} /> Exception Summary</div>
            <div className="exd-meta-grid">
              <div className="exd-meta-item">
                <div className="exd-meta-label">Exception ID</div>
                <div className="exd-meta-val exd-mono">EXC-{runId}-{String(runData?.exceptions?.indexOf(exception) + 1).padStart(4, '0')}</div>
              </div>
              <div className="exd-meta-item">
                <div className="exd-meta-label">Settlement ID</div>
                <div className="exd-meta-val exd-mono">{exception.reference_id || '—'}</div>
              </div>
              <div className="exd-meta-item">
                <div className="exd-meta-label">Expected Amount</div>
                <div className="exd-meta-val exd-bold">{fmtAmount(expectedAmountPaise)}</div>
              </div>
              <div className="exd-meta-item">
                <div className="exd-meta-label">Detected Amount</div>
                <div className="exd-meta-val exd-bold exd-text-red">{fmtAmount(detectedAmountPaise)}</div>
              </div>
              <div className="exd-meta-item">
                <div className="exd-meta-label">Difference</div>
                <div className="exd-meta-val exd-bold exd-text-red">{fmtAmount(differencePaise)}</div>
              </div>
              <div className="exd-meta-item">
                <div className="exd-meta-label">Settlement Date</div>
                <div className="exd-meta-val">{fmtDt(runData?.summary?.run_at)}</div>
              </div>
              <div className="exd-meta-item">
                <div className="exd-meta-label">Expected Credit Date</div>
                <div className="exd-meta-val">{new Date(runData?.summary?.run_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</div>
              </div>
              <div className="exd-meta-item">
                <div className="exd-meta-label">Bank Source</div>
                <div className="exd-meta-val">Bank ledger upload</div>
              </div>
              <div className="exd-meta-item">
                <div className="exd-meta-label">Age</div>
                <div className="exd-meta-val">{ageOf(runData?.summary?.run_at)}</div>
              </div>
              <div className="exd-meta-item">
                <div className="exd-meta-label">Assigned To</div>
                <div className="exd-meta-val">
                  <span className="exd-assign-text">{assignedTo}</span>
                  <button className="exd-assign-btn" onClick={handleAssign}>Assign</button>
                </div>
              </div>
            </div>
            
            {/* AI Conclusion */}
            <div className="exd-ai-conclusion">
              <div className="exd-ai-title">AI Conclusion</div>
              <div className="exd-ai-text">
                "{exception.detail || exception.recommended_action || 'No matching bank credit was found within the expected settlement window (±2 days). This requires human verification.'}"
              </div>
              <div className="exd-ai-confidence">Confidence: {exception?.investigation?.confidence != null ? Math.round(exception.investigation.confidence * 100) : match?.confidence != null ? Math.round(match.confidence * 100) : '—'}%</div>
            </div>
          </div>

          {/* Section 2: Evidence Comparison */}
          <div className="exd-card">
            <div className="exd-card-title"><ShieldCheck size={14} /> Evidence Comparison</div>
            <div className="exd-evidence-grid">
              {/* Razorpay Settlement */}
              <div className="exd-evidence-card exd-evidence-rp">
                <div className="exd-evidence-header">
                  <span className="exd-evidence-dot rp-dot" />
                  <span className="exd-evidence-title">Razorpay Settlement</span>
                </div>
                <div className="exd-evidence-body">
                  <div className="exd-evidence-row">
                    <span>Settlement ID</span>
                    <span className="exd-mono">{exception.reference_id}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Razorpay Amount</span>
                    <span className="exd-bold">{fmtAmount(expectedAmountPaise)}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Settlement Date</span>
                    <span>{fmtDt(runData?.summary?.run_at)}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Reference / Reason</span>
                    <span className="exd-evidence-narration">{match?.reason || exception.detail || 'No persisted reference text recorded'}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Status</span>
                    <span className="exd-status-verified">Settled</span>
                  </div>
                </div>
              </div>

              {/* Bank Statement */}
              <div className="exd-evidence-card exd-evidence-bank">
                <div className="exd-evidence-header">
                  <span className="exd-evidence-dot bank-dot" />
                  <span className="exd-evidence-title">Bank Statement</span>
                </div>
                <div className="exd-evidence-body">
                  {isMissingCredit || !match ? (
                    <div className="exd-evidence-empty">
                      <AlertCircle size={20} color="#e11d48" />
                      <div className="exd-evidence-empty-text">
                        <strong>No Matching Credit Found</strong>
                        <span>Searched from: {new Date(new Date(runData?.summary?.run_at).getTime() - 2*24*60*60*1000).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })} to {new Date(new Date(runData?.summary?.run_at).getTime() + 2*24*60*60*1000).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}</span>
                        <span>Expected Amount: {fmtAmount(expectedAmountPaise)}</span>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="exd-evidence-row">
                        <span>Ledger Entry</span>
                        <span className="exd-mono">{match.matched_entry_id}</span>
                      </div>
                      <div className="exd-evidence-row">
                        <span>Transferred to Bank</span>
                        <span className="exd-bold">{fmtAmount(detectedAmountPaise)}</span>
                      </div>
                      <div className="exd-evidence-row">
                        <span>Date</span>
                        <span>{fmtDt(runData?.summary?.run_at)}</span>
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Matching Engine Result */}
              <div className="exd-evidence-card exd-evidence-engine">
                <div className="exd-evidence-header">
                  <span className="exd-evidence-dot engine-dot" />
                  <span className="exd-evidence-title">Matching Engine Result</span>
                </div>
                <div className="exd-evidence-body">
                  <div className="exd-evidence-row">
                    <span>Match Status</span>
                    <span className={match ? 'exd-status-verified' : 'exd-status-no-match'}>{match ? 'Matched' : 'No Match'}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Match Type</span>
                    <span>{match ? matchLabel : '—'}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Matching Signals</span>
                    <span>{match ? matchLabel : 'No persisted match signals'}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Amount Matched</span>
                    <span>{fmtAmount(detectedAmountPaise)}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Amount Gap</span>
                    <span>{fmtAmount(differencePaise)}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Reason</span>
                    <span className="exd-evidence-reason">{match?.reason || exception.detail || 'No corresponding bank credit found'}</span>
                  </div>
                  <div className="exd-evidence-row">
                    <span>Confidence</span>
                    <span className="exd-bold">{match?.confidence != null ? Math.round(match.confidence * 100) : exception?.investigation?.confidence != null ? Math.round(exception.investigation.confidence * 100) : '—'}%</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Section 3: Matching Signals Checked */}
          <div className="exd-card">
            <div className="exd-card-title"><Cpu size={14} /> Matching Signals Checked</div>
            <div className="exd-signals-list">
              <div className="exd-signal-item">
                <div className="exd-signal-label">Amount Match</div>
                <div className="exd-signal-status exd-signal-failed">
                  <XCircle size={12} /> Not matched
                </div>
              </div>
              <div className="exd-signal-item">
                <div className="exd-signal-label">Reference Match</div>
                <div className="exd-signal-status exd-signal-failed">
                  <XCircle size={12} /> Not matched
                </div>
              </div>
              <div className="exd-signal-item">
                <div className="exd-signal-label">Date Window (±2 days)</div>
                <div className="exd-signal-status exd-signal-failed">
                  <XCircle size={12} /> No credit found
                </div>
              </div>
              <div className="exd-signal-item">
                <div className="exd-signal-label">Counterparty / Account</div>
                <div className="exd-signal-status exd-signal-na">
                  <span>—</span> Not applicable
                </div>
              </div>
              <div className="exd-signal-item">
                <div className="exd-signal-label">Fuzzy / Narration Match</div>
                <div className="exd-signal-status exd-signal-failed">
                  <XCircle size={12} /> Not matched
                </div>
              </div>
            </div>
          </div>

          {/* Section 4: Investigator Notes */}
          <div className="exd-card">
            <div className="exd-card-title"><FileText size={14} /> Investigator Notes</div>
            <div className="exd-notes-section">
              <textarea
                className="exd-notes-textarea"
                placeholder="Add notes here..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={4}
              />
              <div className="exd-notes-actions">
                <div className="exd-attachment-section">
                  <input
                    type="file"
                    id="file-upload"
                    className="exd-file-input"
                    accept=".csv,.pdf,.jpg,.jpeg,.png"
                    onChange={handleFileUpload}
                  />
                  <label htmlFor="file-upload" className="exd-attachment-btn">
                    <Paperclip size={14} /> Upload File
                  </label>
                  <span className="exd-attachment-hint">CSV, PDF, JPG up to 5MB</span>
                  {attachment && (
                    <div className="exd-attached-file">
                      <FileCheck size={12} />
                      <span>{attachment.name}</span>
                      <button onClick={() => setAttachment(null)} className="exd-remove-file">
                        <XCircle size={12} />
                      </button>
                    </div>
                  )}
                </div>
                <button className="btn-primary exd-save-notes-btn" onClick={handleSaveNotes}>
                  Save Notes
                </button>
              </div>
            </div>
          </div>

          {/* Section 5: Actions */}
          {showActions && (
            <div className="exd-card exd-actions-card">
              <div className="exd-card-title">Actions</div>
              {resolveError && <div className="inv-error-note"><AlertTriangle size={13} /> {resolveError}</div>}
              <div className="exd-action-buttons">
                <button 
                  className="exd-action-btn exd-action-resolve" 
                  onClick={() => resolve('approve')}
                  disabled={resolving}
                >
                  <CheckCircle2 size={14} /> Mark as Resolved
                </button>
                <button 
                  className="exd-action-btn exd-action-escalate" 
                  onClick={() => resolve('escalate')}
                  disabled={resolving}
                >
                  <Flag size={14} /> Escalate
                </button>
                <button 
                  className="exd-action-btn exd-action-review" 
                  onClick={() => resolve('reviewed')}
                  disabled={resolving}
                >
                  <Eye size={14} /> Mark as Reviewed
                </button>
                <button 
                  className="exd-action-btn exd-action-reject" 
                  onClick={() => resolve('reject')}
                  disabled={resolving}
                >
                  <ThumbsDown size={14} /> Reject
                </button>
              </div>
            </div>
          )}

          {/* Section 6: Investigation Details */}
          <div className="exd-card">
            <div className="exd-card-title"><Search size={14} /> Investigation Details</div>
            <div className="exd-investigation-grid">
              <div className="exd-investigation-item">
                <div className="exd-investigation-label">Detected By</div>
                <div className="exd-investigation-val">{exception?.source || '—'}</div>
              </div>
              <div className="exd-investigation-item">
                <div className="exd-investigation-label">Detected At</div>
                <div className="exd-investigation-val">{fmtDt(runData?.summary?.run_at)}</div>
              </div>
              <div className="exd-investigation-item">
                <div className="exd-investigation-label">Rule / Model</div>
                <div className="exd-investigation-val">{match ? `${match.tier}${match.match_subtype ? ` · ${match.match_subtype}` : ''}` : exception?.exception_type || 'No match recorded'}</div>
              </div>
              <div className="exd-investigation-item">
                <div className="exd-investigation-label">Processed in Run</div>
                <div className="exd-investigation-val">#{runId}</div>
              </div>
              <div className="exd-investigation-item">
                <div className="exd-investigation-label">Auto-Resolution</div>
                <div className="exd-investigation-val">{isAutoResolved(currentStatus) ? 'Applied' : 'Not applied'}</div>
              </div>
            </div>
          </div>

          {/* Section 7: Audit Trail */}
          <div className="exd-card">
            <div className="exd-card-title-row">
              <div className="exd-card-title"><Clock size={14} /> Audit Trail</div>
              <Link to="#" className="exd-view-full-link">View full audit log →</Link>
            </div>
            <div className="exd-audit-trail">
              {auditEntries.map((entry, i) => (
                <div key={i} className="exd-audit-item">
                  <div className={`exd-audit-dot ${entry.action === 'approve' ? 'exd-audit-green' : entry.action === 'escalate' ? 'exd-audit-red' : 'exd-audit-blue'}`} />
                  <div className="exd-audit-content">
                    <div className="exd-audit-action">{entry.action}</div>
                    <div className="exd-audit-time">{fmtDt(entry.at)}</div>
                    <div className="exd-audit-actor">{entry.by}</div>
                    {entry.detail && <div className="exd-audit-detail">{entry.detail}</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Section 8: Why This Was Flagged */}
          <div className="exd-card exd-why-card">
            <div className="exd-card-title"><AlertCircle size={14} /> Why This Was Flagged</div>
            <div className="exd-why-text">
              {match
                ? `Razorpay expected ${fmtAmount(expectedAmountPaise)} and the matched bank transfer was ${fmtAmount(detectedAmountPaise)}${differencePaise ? `, leaving a difference of ${fmtAmount(differencePaise)}` : ''}. ${match.reason || ''}`
                : `The system expected a bank credit of ${fmtAmount(expectedAmountPaise)} based on the settlement report, but no matching credit was found in the bank statement within the expected date window.`}
            </div>
          </div>
        </div>

        {/* Side Column */}
        <div className="exd-side-col">
          <div className="exd-side-card">
            <div className="exd-side-title">In This Run</div>
            <Link to={`/reconciliations/${runId}`} className="exd-side-link">
              <FileText size={13} /> Run #{String(runId).padStart(3, '0')} details <ChevronRight size={12} />
            </Link>
            <Link to={`/reconciliations/${runId}#report`} className="exd-side-link">
              <AlertTriangle size={13} /> All exceptions for this run <ChevronRight size={12} />
            </Link>
          </div>

          <div className="exd-side-card">
            <div className="exd-side-title">Quick Info</div>
            <div className="exd-side-stat">
              <span className="exd-side-stat-label">Run</span>
              <span className="exd-side-stat-val">#{String(runId).padStart(3, '0')}</span>
            </div>
            <div className="exd-side-stat">
              <span className="exd-side-stat-label">Total exceptions</span>
              <span className="exd-side-stat-val">{runData?.exceptions?.length ?? '—'}</span>
            </div>
            <div className="exd-side-stat">
              <span className="exd-side-stat-label">Expected amount</span>
              <span className="exd-side-stat-val">{fmtAmount(exception.amount_paise)}</span>
            </div>
            <div className="exd-side-stat">
              <span className="exd-side-stat-label">Severity</span>
              <span className="exd-side-stat-val"><SevBadge level={sev} /></span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}